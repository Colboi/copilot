from __future__ import annotations

import configparser
import json
from pathlib import Path
from threading import RLock
from typing import Callable, Mapping


class UserConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._lock = RLock()

    def read_section(self, section: str) -> dict[str, str]:
        with self._lock:
            parser = self._read_parser_locked()
            if not parser.has_section(section):
                return {}
            return dict(parser.items(section, raw=True))

    def update_section(self, section: str, values: Mapping[str, object]) -> None:
        if not section:
            raise ValueError('配置节名称不能为空')
        if not values:
            raise ValueError('配置更新内容不能为空')

        with self._lock:
            parser = self._read_parser_locked()
            if not parser.has_section(section):
                parser.add_section(section)
            for key, value in values.items():
                if not isinstance(key, str) or not key:
                    raise ValueError('配置项名称必须是非空文本')
                parser.set(section, key, self._serialize_value(value))
            self._write_parser_locked(parser)

    def migrate_section_from(self, source_store: UserConfigStore, section: str) -> bool:
        if source_store.path == self.path:
            return False

        values = source_store.read_section(section)
        if not values:
            return False

        with self._lock:
            parser = self._read_parser_locked()
            if parser.has_section(section):
                return False
            parser.add_section(section)
            for key, value in values.items():
                parser.set(section, key, value)
            self._write_parser_locked(parser)

        source_store.remove_section(section)
        return True

    def remove_section(self, section: str) -> bool:
        with self._lock:
            parser = self._read_parser_locked()
            if not parser.remove_section(section):
                return False
            self._write_parser_locked(parser)
            return True

    def migrate_json_section(
        self,
        section: str,
        legacy_path: Path,
        allowed_keys: set[str],
        should_migrate: Callable[[dict[str, object]], bool] | None = None,
    ) -> bool:
        with self._lock:
            parser = self._read_parser_locked()
            if parser.has_section(section) or not legacy_path.is_file():
                return False

            try:
                raw = json.loads(legacy_path.read_text(encoding='utf-8'))
            except OSError as error:
                raise ValueError(f'无法读取旧配置文件：{legacy_path}') from error
            except json.JSONDecodeError as error:
                raise ValueError(f'旧配置文件格式错误：{legacy_path}') from error
            if not isinstance(raw, dict):
                raise ValueError(f'旧配置文件必须包含对象：{legacy_path}')
            if should_migrate is not None and not should_migrate(raw):
                return False

            values = {key: raw[key] for key in allowed_keys if key in raw}
            if not values:
                return False
            if not parser.has_section(section):
                parser.add_section(section)
            for key, value in values.items():
                parser.set(section, key, self._serialize_value(value))
            self._write_parser_locked(parser)
            return True

    def _read_parser_locked(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        if self.path.is_file():
            try:
                with self.path.open('r', encoding='utf-8') as stream:
                    parser.read_file(stream)
            except OSError as error:
                raise ValueError(f'无法读取配置文件：{self.path}') from error
            except configparser.Error as error:
                raise ValueError(f'配置文件格式错误：{self.path}') from error
        return parser

    def _write_parser_locked(self, parser: configparser.ConfigParser) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('w', encoding='utf-8', newline='\n') as stream:
                parser.write(stream)
        except OSError as error:
            raise ValueError(f'无法保存配置文件：{self.path}') from error

    @staticmethod
    def _serialize_value(value: object) -> str:
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return str(value)
        raise ValueError(f'配置项值类型不受支持：{type(value).__name__}')
