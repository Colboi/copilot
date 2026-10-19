from __future__ import annotations

import io
import json
import re
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from backend.user_config import UserConfigStore


PLUGIN_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
GITHUB_HOST = 'github.com'
GITHUB_API_ROOT = 'https://api.github.com'
DEFAULT_UPDATE_INTERVAL_MINUTES = 120
MIN_UPDATE_INTERVAL_MINUTES = 5
MAX_UPDATE_INTERVAL_MINUTES = 1440
MAX_PLUGIN_ARCHIVE_BYTES = 100 * 1024 * 1024
SOURCE_SECTION = 'plugin_sources'
PLUGIN_MANAGER_SECTION = 'plugin_manager'
COLPILOT_VERSION = '0.1.0'


class PluginRepositoryManager:
    def __init__(self, plugin_root: Path, config_store: UserConfigStore) -> None:
        self.plugin_root = plugin_root.expanduser().resolve()
        self.config_store = config_store
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.plugin_root.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._run_periodic_checks,
            name='colpilot-plugin-update-checker',
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def list_installed(self) -> list[dict[str, object]]:
        source_records = self._read_source_records()
        installed: list[dict[str, object]] = []
        for manifest_path in sorted(self.plugin_root.glob('*/manifest.json')):
            manifest = self._read_manifest(manifest_path)
            plugin_id = manifest.get('id')
            if not isinstance(plugin_id, str) or not plugin_id:
                raise ValueError(f'插件清单标识无效：{manifest_path}')

            record = source_records.get(plugin_id, {})
            status = record.get('status', 'untracked')
            if not isinstance(status, str):
                raise ValueError(f'插件来源状态无效：{plugin_id}')
            source_type = record.get(
                'source_type',
                'github' if record.get('url') else 'local',
            )
            source_url = record.get('display_url', record.get('url', ''))
            error_message = record.get('error', '')
            if (
                not isinstance(source_type, str)
                or source_type not in {'github', 'zip', 'local'}
                or not isinstance(source_url, str)
                or not isinstance(error_message, str)
            ):
                raise ValueError(f'插件来源记录无效：{plugin_id}')

            installed.append(
                {
                    'id': plugin_id,
                    'name': self._manifest_text(manifest, 'name', plugin_id),
                    'description': self._manifest_text(manifest, 'description', plugin_id),
                    'source_url': source_url,
                    'source_type': source_type,
                    'status': status,
                    'status_label': self._status_label(status),
                    'checked_at': record.get('checked_at', ''),
                    'installed_sha': record.get('installed_sha', ''),
                    'latest_sha': record.get('latest_sha', ''),
                    'error': error_message,
                }
            )
        return installed

    def install_from_github_url(self, repository_url: str) -> dict[str, object]:
        normalized_url = self.normalize_github_url(repository_url)
        repository, latest_sha = self._read_repository_state(normalized_url)
        archive = self._download_repository_archive(repository, normalized_url)
        return self._install_archive(
            archive,
            {
                'url': normalized_url,
                'source_type': 'github',
                'installed_sha': latest_sha,
                'latest_sha': latest_sha,
                'status': 'latest',
                'checked_at': self._timestamp(),
            },
        )

    def install_from_zip_archive(self, archive_name: str, archive: bytes) -> dict[str, object]:
        if not isinstance(archive_name, str) or not archive_name.strip():
            raise ValueError('插件 ZIP 文件名称不能为空')
        normalized_name = archive_name.strip().replace('\\', '/')
        safe_name = normalized_name.rsplit('/', 1)[-1]
        if not safe_name or safe_name in {'.', '..'}:
            raise ValueError('插件 ZIP 文件名称无效')
        if not safe_name.lower().endswith('.zip'):
            raise ValueError('插件导入文件必须是 ZIP 文件')

        return self._install_archive(
            archive,
            {
                'url': '',
                'display_url': f'本地 ZIP：{safe_name}',
                'source_type': 'zip',
                'installed_sha': '',
                'latest_sha': '',
                'status': 'local',
                'checked_at': self._timestamp(),
            },
        )

    def _install_archive(
        self,
        archive: bytes,
        source_record: dict[str, object],
    ) -> dict[str, object]:
        staging_path, manifest = self._extract_archive(archive)
        moved_path: Path | None = None
        try:
            self._validate_downloaded_manifest(manifest)
            plugin_id = manifest['id']
            if not isinstance(plugin_id, str):
                raise ValueError('插件标识必须是文本')
            final_path = self.plugin_root / plugin_id
            if final_path.exists():
                raise ValueError(f'插件已经安装：{plugin_id}')

            staging_path.replace(final_path)
            moved_path = final_path
            source_records = self._read_source_records()
            source_records[plugin_id] = source_record
            self._write_source_records(source_records)
            source_url = source_record.get(
                'display_url',
                source_record.get('url', ''),
            )
            if not isinstance(source_url, str):
                raise ValueError(f'插件来源地址无效：{plugin_id}')
            installed_sha = source_record.get('installed_sha', '')
            if not isinstance(installed_sha, str):
                raise ValueError(f'插件安装提交标识无效：{plugin_id}')
            return {
                'id': plugin_id,
                'name': manifest['name'],
                'source_url': source_url,
                'source_type': source_record.get('source_type', 'local'),
                'installed_sha': installed_sha,
                'requires_restart': True,
            }
        except BaseException:
            if moved_path is not None and moved_path.exists():
                shutil.rmtree(moved_path)
            raise
        finally:
            if staging_path.exists():
                shutil.rmtree(staging_path)

    def check_updates(self) -> list[dict[str, object]]:
        source_records = self._read_source_records()
        if not source_records:
            return self.list_installed()

        changed = False
        for plugin_id, record in source_records.items():
            source_type = record.get('source_type', 'github')
            if not isinstance(source_type, str):
                raise ValueError(f'插件来源类型无效：{plugin_id}')
            if source_type == 'zip':
                if record.get('status') != 'local':
                    record['status'] = 'local'
                    changed = True
                continue
            if source_type != 'github':
                raise ValueError(f'插件来源类型无效：{plugin_id}')
            repository_url = record.get('url')
            if not isinstance(repository_url, str) or not repository_url:
                raise ValueError(f'插件来源地址无效：{plugin_id}')
            try:
                normalized_url = self.normalize_github_url(repository_url)
                _, latest_sha = self._read_repository_state(normalized_url)
                installed_sha = record.get('installed_sha')
                if not isinstance(installed_sha, str) or not installed_sha:
                    raise ValueError(f'插件安装提交标识缺失：{plugin_id}')
                record.update(
                    {
                        'url': normalized_url,
                        'latest_sha': latest_sha,
                        'status': 'latest' if installed_sha == latest_sha else 'needs_update',
                        'checked_at': self._timestamp(),
                        'error': '',
                    }
                )
            except ValueError as error:
                record.update(
                    {
                        'status': 'error',
                        'checked_at': self._timestamp(),
                        'error': str(error),
                    }
                )
            changed = True

        if changed:
            self._write_source_records(source_records)
        return self.list_installed()

    def get_update_interval(self) -> int:
        raw_value = self.config_store.read_section(PLUGIN_MANAGER_SECTION).get(
            'update_interval_minutes'
        )
        if raw_value is None:
            return DEFAULT_UPDATE_INTERVAL_MINUTES
        try:
            minutes = int(raw_value)
        except ValueError as error:
            raise ValueError('插件更新检查间隔必须是整数') from error
        return self._validate_update_interval(minutes)

    def set_update_interval(self, minutes: int) -> int:
        if isinstance(minutes, bool):
            raise ValueError('插件更新检查间隔必须是整数')
        validated_minutes = self._validate_update_interval(minutes)
        self.config_store.update_section(
            PLUGIN_MANAGER_SECTION,
            {'update_interval_minutes': validated_minutes},
        )
        self._wake_event.set()
        return validated_minutes

    @staticmethod
    def normalize_github_url(repository_url: str) -> str:
        if not isinstance(repository_url, str) or not repository_url.strip():
            raise ValueError('GitHub 仓库地址不能为空')
        parsed = urlparse(repository_url.strip())
        if parsed.scheme.lower() != 'https' or parsed.netloc.lower() != GITHUB_HOST:
            raise ValueError('GitHub 仓库地址必须使用 https://github.com/owner/repository 格式')
        if parsed.query or parsed.fragment:
            raise ValueError('GitHub 仓库地址不能包含查询参数或片段')

        segments = [segment for segment in parsed.path.split('/') if segment]
        if len(segments) != 2:
            raise ValueError('GitHub 仓库地址必须包含 owner 和 repository')
        owner, repository = segments
        if repository.endswith('.git'):
            repository = repository[:-4]
        if not owner or not repository or any('/' in value or '\\' in value for value in (owner, repository)):
            raise ValueError('GitHub 仓库地址包含无效路径')
        return f'https://{GITHUB_HOST}/{owner}/{repository}'

    def _run_periodic_checks(self) -> None:
        while not self._stop_event.is_set():
            self.check_updates()
            wait_seconds = self.get_update_interval() * 60
            self._wake_event.wait(wait_seconds)
            self._wake_event.clear()

    def _read_repository_state(self, repository_url: str) -> tuple[dict[str, object], str]:
        parsed = urlparse(repository_url)
        owner, repository_name = [part for part in parsed.path.split('/') if part]
        api_url = f'{GITHUB_API_ROOT}/repos/{quote(owner)}/{quote(repository_name)}'
        repository = self._request_json(api_url)
        default_branch = repository.get('default_branch')
        if not isinstance(default_branch, str) or not default_branch:
            raise ValueError(f'GitHub 仓库没有有效的默认分支：{repository_url}')

        branch_url = (
            f'{GITHUB_API_ROOT}/repos/{quote(owner)}/{quote(repository_name)}'
            f'/commits/{quote(default_branch, safe="")}'
        )
        commit = self._request_json(branch_url)
        latest_sha = commit.get('sha')
        if not isinstance(latest_sha, str) or not latest_sha:
            raise ValueError(f'无法读取 GitHub 仓库提交标识：{repository_url}')
        return repository, latest_sha

    def _download_repository_archive(
        self,
        repository: dict[str, object],
        repository_url: str,
    ) -> bytes:
        archive_url = repository.get('zipball_url')
        if not isinstance(archive_url, str) or not archive_url:
            parsed = urlparse(repository_url)
            owner, repository_name = [part for part in parsed.path.split('/') if part]
            default_branch = repository.get('default_branch')
            if not isinstance(default_branch, str) or not default_branch:
                raise ValueError(f'GitHub 仓库没有可下载分支：{repository_url}')
            archive_url = (
                f'{GITHUB_API_ROOT}/repos/{quote(owner)}/{quote(repository_name)}'
                f'/zipball/{quote(default_branch, safe="")}'
            )

        headers = self._github_headers()
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
                response = client.get(archive_url)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise ValueError(f'无法下载 GitHub 插件仓库：{repository_url}') from error
        if not response.content:
            raise ValueError(f'GitHub 插件仓库下载内容为空：{repository_url}')
        if len(response.content) > MAX_PLUGIN_ARCHIVE_BYTES:
            raise ValueError('插件压缩包超过 100 MB，无法安装')
        return response.content

    def _request_json(self, url: str) -> dict[str, object]:
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True, headers=self._github_headers()) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise ValueError(f'无法访问 GitHub：{url}') from error
        try:
            payload = response.json()
        except ValueError as error:
            raise ValueError(f'GitHub 返回内容格式无效：{url}') from error
        if not isinstance(payload, dict):
            raise ValueError(f'GitHub 返回内容类型无效：{url}')
        return payload

    @staticmethod
    def _github_headers() -> dict[str, str]:
        return {
            'Accept': 'application/vnd.github+json',
            'User-Agent': f'Colpilot/{COLPILOT_VERSION}',
        }

    def _extract_archive(self, archive: bytes) -> tuple[Path, dict[str, object]]:
        if not isinstance(archive, bytes) or not archive:
            raise ValueError('插件压缩包内容不能为空')
        if len(archive) > MAX_PLUGIN_ARCHIVE_BYTES:
            raise ValueError('插件压缩包超过 100 MB，无法安装')
        staging_path = self.plugin_root / f'.colpilot-plugin-install-{uuid.uuid4().hex}'
        staging_path.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as archive_file:
                members = archive_file.infolist()
                manifest_members = [
                    member
                    for member in members
                    if not member.is_dir()
                    and (
                        self._normalise_member_name(member.filename).endswith('/manifest.json')
                        or self._normalise_member_name(member.filename) == 'manifest.json'
                    )
                ]
                if len(manifest_members) != 1:
                    raise ValueError('插件压缩包必须包含一个 manifest.json')

                manifest_member = manifest_members[0]
                manifest_name = self._normalise_member_name(manifest_member.filename)
                archive_root = manifest_name.rsplit('/', 1)[0] if '/' in manifest_name else ''
                archive_prefix = f'{archive_root}/' if archive_root else ''
                manifest_bytes = archive_file.read(manifest_member)
                try:
                    manifest = json.loads(manifest_bytes.decode('utf-8'))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ValueError('插件 manifest.json 格式无效') from error
                if not isinstance(manifest, dict):
                    raise ValueError('插件 manifest.json 必须包含对象')

                for member in members:
                    member_name = self._normalise_member_name(member.filename)
                    if not member_name:
                        continue
                    if archive_prefix and not (
                        member_name == archive_root
                        or member_name.startswith(archive_prefix)
                    ):
                        raise ValueError('插件压缩包包含多个顶层目录')
                    relative_name = member_name[len(archive_prefix):] if archive_prefix else member_name
                    if not relative_name:
                        continue
                    relative_parts = relative_name.split('/')
                    if any(
                        part in {'.', '..'} or ':' in part
                        for part in relative_parts
                    ):
                        raise ValueError('插件压缩包包含无效文件路径')
                    if relative_name.lower().endswith('config.ini'):
                        raise ValueError('插件压缩包不能包含用户配置文件')
                    if self._is_symbolic_link(member):
                        raise ValueError('插件压缩包不能包含符号链接')

                    destination = staging_path.joinpath(*relative_parts)
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive_file.open(member, 'r') as source, destination.open('wb') as target:
                        shutil.copyfileobj(source, target)

            return staging_path, manifest
        except BaseException:
            if staging_path.exists():
                shutil.rmtree(staging_path)
            raise

    @staticmethod
    def _normalise_member_name(name: str) -> str:
        normalised = name.replace('\\', '/')
        if normalised.startswith('/') or re.match(r'^[A-Za-z]:/', normalised):
            raise ValueError('插件压缩包包含绝对路径')
        parts = [part for part in normalised.split('/') if part]
        if any(part in {'.', '..'} or ':' in part for part in parts):
            raise ValueError('插件压缩包包含无效文件路径')
        return normalised.rstrip('/')

    @staticmethod
    def _is_symbolic_link(member: zipfile.ZipInfo) -> bool:
        unix_mode = (member.external_attr >> 16) & 0o170000
        return unix_mode == 0o120000

    def _validate_downloaded_manifest(self, manifest: dict[str, object]) -> None:
        required_text_keys = (
            'id',
            'name',
            'description',
            'category',
            'color',
            'tool_type',
            'view',
            'frontend',
            'backend',
        )
        for key in required_text_keys:
            value = manifest.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f'插件 manifest 缺少有效项目：{key}')
        plugin_id = manifest['id']
        if not isinstance(plugin_id, str) or not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise ValueError('插件标识只能包含英文字母、数字、点、下划线和连字符')
        if manifest['tool_type'] not in {'continuous', 'on_demand'}:
            raise ValueError('插件 tool_type 无效')
        icon = manifest.get('icon')
        if icon is not None and not isinstance(icon, str):
            raise ValueError('插件 icon 必须是文本或空值')

    @staticmethod
    def _read_manifest(manifest_path: Path) -> dict[str, object]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f'无法读取插件清单：{manifest_path}') from error
        if not isinstance(manifest, dict):
            raise ValueError(f'插件清单必须包含对象：{manifest_path}')
        return manifest

    @staticmethod
    def _manifest_text(manifest: dict[str, object], key: str, plugin_id: str) -> str:
        value = manifest.get(key)
        if not isinstance(value, str):
            raise ValueError(f'插件清单项目无效：{plugin_id}.{key}')
        return value

    def _read_source_records(self) -> dict[str, dict[str, object]]:
        raw_records = self.config_store.read_section(SOURCE_SECTION)
        records: dict[str, dict[str, object]] = {}
        for plugin_id, raw_record in raw_records.items():
            try:
                record = json.loads(raw_record)
            except json.JSONDecodeError as error:
                raise ValueError(f'插件来源记录格式无效：{plugin_id}') from error
            if not isinstance(record, dict):
                raise ValueError(f'插件来源记录必须包含对象：{plugin_id}')
            records[plugin_id] = record
        return records

    def _write_source_records(self, records: dict[str, dict[str, object]]) -> None:
        if not records:
            self.config_store.remove_section(SOURCE_SECTION)
            return
        self.config_store.update_section(
            SOURCE_SECTION,
            {
                plugin_id: json.dumps(record, ensure_ascii=False, sort_keys=True)
                for plugin_id, record in records.items()
            },
        )

    @staticmethod
    def _status_label(status: str) -> str:
        labels = {
            'latest': '【已是最新】',
            'needs_update': '【需要更新】',
            'error': '【检查失败】',
            'untracked': '【未记录来源】',
            'local': '【本地压缩包】',
        }
        return labels.get(status, '【等待检查】')

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec='seconds')

    @staticmethod
    def _validate_update_interval(minutes: int) -> int:
        if not isinstance(minutes, int):
            raise ValueError('插件更新检查间隔必须是整数')
        if not MIN_UPDATE_INTERVAL_MINUTES <= minutes <= MAX_UPDATE_INTERVAL_MINUTES:
            raise ValueError(
                f'插件更新检查间隔需要在 {MIN_UPDATE_INTERVAL_MINUTES} 到 '
                f'{MAX_UPDATE_INTERVAL_MINUTES} 分钟之间'
            )
        return minutes
