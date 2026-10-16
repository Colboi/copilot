import argparse
import json
import sys
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.user_config import UserConfigStore
from backend.process_manager import ManagedProcessRegistry


BACKEND_PORT = 37651
PLUGIN_ROOT = PROJECT_ROOT / 'plugins'
TOOL_TYPES = {'continuous', 'on_demand'}


class PluginRuntime(BaseModel):
    status: Literal['running', 'stopped', 'error']
    detail: str
    exit_code: int | None = None


class PluginDescriptor(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    color: str
    tool_type: Literal['continuous', 'on_demand']
    enabled: bool
    view: str = 'generic'
    runtime: PluginRuntime | None = None


class PluginToggleRequest(BaseModel):
    enabled: bool


class PluginOrderRequest(BaseModel):
    order: list[str]


class PluginRunRequest(BaseModel):
    arguments: dict[str, object] = Field(default_factory=dict)


class CommandRequest(BaseModel):
    command: Literal['exit']


def load_plugin_manifests() -> tuple[list[dict[str, object]], dict[str, Path]]:
    manifests: list[dict[str, object]] = []
    plugin_roots: dict[str, Path] = {}
    for manifest_path in sorted(PLUGIN_ROOT.glob('*/manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError(f'Plugin manifest must contain an object: {manifest_path}')
        plugin_id = manifest.get('id')
        if not isinstance(plugin_id, str) or not plugin_id:
            raise ValueError(f'Plugin manifest id is invalid: {manifest_path}')
        if plugin_id in plugin_roots:
            raise ValueError(f'Duplicate plugin id: {plugin_id}')
        tool_type = manifest.get('tool_type')
        if not isinstance(tool_type, str) or tool_type not in TOOL_TYPES:
            raise ValueError(f'Plugin tool_type is invalid: {manifest_path}')
        plugin_roots[plugin_id] = manifest_path.parent
        manifests.append(manifest)
    return manifests, plugin_roots


def load_plugin_handlers(
    manifests: list[dict[str, object]],
    plugin_roots: dict[str, Path],
    program_config_store: UserConfigStore,
    process_registry: ManagedProcessRegistry,
) -> dict[str, Any]:
    handlers: dict[str, Any] = {}
    for manifest in manifests:
        plugin_id = manifest['id']
        backend_entry = manifest.get('backend')
        if backend_entry is None:
            raise ValueError(f'Plugin backend entry is missing: {plugin_id}')
        if not isinstance(plugin_id, str) or not isinstance(backend_entry, str):
            raise ValueError(f'Plugin backend entry is invalid: {plugin_id}')
        module_name, separator, factory_name = backend_entry.partition(':')
        if not separator or not module_name or not factory_name:
            raise ValueError(f'Plugin backend entry must use module:factory format: {plugin_id}')
        module = import_module(module_name)
        factory = getattr(module, factory_name)
        plugin_config_store = UserConfigStore(plugin_roots[plugin_id] / 'config.ini')
        plugin_config_store.migrate_section_from(program_config_store, plugin_id)
        handler = factory(plugin_roots[plugin_id], plugin_config_store, process_registry)
        required_methods = (
            ('start', 'stop', 'runtime_status')
            if manifest['tool_type'] == 'continuous'
            else ('run',)
        )
        missing_methods = [
            method_name
            for method_name in required_methods
            if not callable(getattr(handler, method_name, None))
        ]
        if missing_methods:
            raise ValueError(
                f'Plugin handler is missing methods for {plugin_id}: '
                f'{", ".join(missing_methods)}'
            )
        handlers[plugin_id] = handler
    return handlers


PLUGIN_DEFINITIONS, PLUGIN_ROOTS = load_plugin_manifests()
PLUGIN_HANDLERS: dict[str, Any] = {}
PROGRAM_CONFIG_STORE: UserConfigStore | None = None
PLUGIN_PROCESS_REGISTRY = ManagedProcessRegistry()
enabled_plugins = {plugin['id']: True for plugin in PLUGIN_DEFINITIONS}
plugin_order = [plugin['id'] for plugin in PLUGIN_DEFINITIONS]


def configure_runtime(config_path: Path) -> None:
    global PLUGIN_HANDLERS, PROGRAM_CONFIG_STORE
    resolved_path = config_path.expanduser().resolve()
    if PROGRAM_CONFIG_STORE is not None and PROGRAM_CONFIG_STORE.path == resolved_path:
        return
    PROGRAM_CONFIG_STORE = UserConfigStore(resolved_path)
    PLUGIN_HANDLERS = load_plugin_handlers(
        PLUGIN_DEFINITIONS,
        PLUGIN_ROOTS,
        PROGRAM_CONFIG_STORE,
        PLUGIN_PROCESS_REGISTRY,
    )
    enabled_plugins.clear()
    enabled_plugins.update(_read_enabled_plugins(PROGRAM_CONFIG_STORE))
    plugin_order.clear()
    plugin_order.extend(_read_plugin_order(PROGRAM_CONFIG_STORE))


def _read_enabled_plugins(config_store: UserConfigStore) -> dict[str, bool]:
    raw_settings = config_store.read_section('colpilot')
    supported_keys = {
        'plugin_order',
        *(f'enabled_{plugin["id"]}' for plugin in PLUGIN_DEFINITIONS),
    }
    unknown_keys = sorted(set(raw_settings) - supported_keys)
    if unknown_keys:
        raise ValueError(f'unsupported saved settings: {", ".join(unknown_keys)}')

    enabled: dict[str, bool] = {}
    for plugin in PLUGIN_DEFINITIONS:
        plugin_id = plugin['id']
        key = f'enabled_{plugin_id}'
        raw_value = raw_settings.get(key)
        if raw_value is None:
            enabled[plugin_id] = True
            continue
        normalised = raw_value.strip().lower()
        if normalised in {'true', '1', 'yes', 'on'}:
            enabled[plugin_id] = True
        elif normalised in {'false', '0', 'no', 'off'}:
            enabled[plugin_id] = False
        else:
            raise ValueError(f'{key} must be a boolean')
    return enabled


def _read_plugin_order(config_store: UserConfigStore) -> list[str]:
    default_order = [plugin['id'] for plugin in PLUGIN_DEFINITIONS]
    raw_order = config_store.read_section('colpilot').get('plugin_order')
    if raw_order is None:
        return default_order

    saved_order = [plugin_id.strip() for plugin_id in raw_order.split(',')]
    if any(not plugin_id for plugin_id in saved_order):
        raise ValueError('plugin_order contains an empty plugin id')
    if len(saved_order) != len(set(saved_order)):
        raise ValueError('plugin_order contains duplicate plugin ids')

    unknown_ids = sorted(set(saved_order) - set(default_order))
    if unknown_ids:
        raise ValueError(f'plugin_order contains unknown plugin ids: {", ".join(unknown_ids)}')

    return saved_order + [
        plugin_id
        for plugin_id in default_order
        if plugin_id not in saved_order
    ]


def _validate_plugin_order(order: list[str]) -> list[str]:
    available_ids = {plugin['id'] for plugin in PLUGIN_DEFINITIONS}
    if len(order) != len(available_ids):
        raise ValueError('plugin order must contain every plugin exactly once')
    if any(not plugin_id for plugin_id in order):
        raise ValueError('plugin order contains an empty plugin id')
    if len(order) != len(set(order)):
        raise ValueError('plugin order contains duplicate plugin ids')
    unknown_ids = sorted(set(order) - available_ids)
    if unknown_ids:
        raise ValueError(f'plugin order contains unknown plugin ids: {", ".join(unknown_ids)}')
    return order


configure_runtime(PROJECT_ROOT / 'config.ini')


def stop_plugin_handlers() -> None:
    handlers = [
        PLUGIN_HANDLERS[plugin['id']]
        for plugin in reversed(PLUGIN_DEFINITIONS)
        if plugin['id'] in PLUGIN_HANDLERS
    ]

    def stop_handler_at(index: int) -> None:
        if index >= len(handlers):
            return
        handler = handlers[index]
        try:
            stop_method = getattr(handler, 'stop', None)
            if callable(stop_method):
                stop_method()
        finally:
            stop_handler_at(index + 1)

    try:
        stop_handler_at(0)
    finally:
        PLUGIN_PROCESS_REGISTRY.stop_all()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        for plugin in PLUGIN_DEFINITIONS:
            if (
                plugin['tool_type'] != 'continuous'
                or not enabled_plugins[plugin['id']]
            ):
                continue
            handler = get_plugin_handler(plugin['id'])
            handler.start()
        yield
    finally:
        stop_plugin_handlers()


app = FastAPI(
    title='Colpilot Backend',
    version='0.1.0',
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://127.0.0.1:1420',
        'http://localhost:1420',
        'tauri://localhost',
        'http://tauri.localhost',
        'https://tauri.localhost',
    ],
    allow_credentials=False,
    allow_private_network=True,
    allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type'],
)


def get_plugin_definition(plugin_id: str) -> dict[str, object]:
    plugin = next((item for item in PLUGIN_DEFINITIONS if item['id'] == plugin_id), None)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f'Unknown plugin: {plugin_id}')
    return plugin


def get_plugin_handler(plugin_id: str) -> Any:
    get_plugin_definition(plugin_id)
    try:
        return PLUGIN_HANDLERS[plugin_id]
    except KeyError as error:
        raise HTTPException(
            status_code=501,
            detail=f'Plugin backend is unavailable: {plugin_id}',
        ) from error


def get_plugin_runtime(plugin_id: str) -> PluginRuntime | None:
    plugin = get_plugin_definition(plugin_id)
    if plugin['tool_type'] != 'continuous':
        return None
    if not enabled_plugins[plugin_id]:
        return PluginRuntime(status='stopped', detail='工具已停用')
    handler = get_plugin_handler(plugin_id)
    return PluginRuntime(**handler.runtime_status())


def build_plugin_descriptor(plugin_id: str) -> PluginDescriptor:
    plugin = get_plugin_definition(plugin_id)
    return PluginDescriptor(
        **plugin,
        enabled=enabled_plugins[plugin_id],
        runtime=get_plugin_runtime(plugin_id),
    )


@app.get('/api/health')
def health() -> dict[str, str]:
    return {'status': 'ok', 'service': 'colpilot-backend'}


@app.get('/api/plugins', response_model=list[PluginDescriptor])
def list_plugins() -> list[PluginDescriptor]:
    return [build_plugin_descriptor(plugin_id) for plugin_id in plugin_order]


@app.post('/api/plugins/order', response_model=list[PluginDescriptor])
def update_plugin_order(request: PluginOrderRequest) -> list[PluginDescriptor]:
    try:
        next_order = _validate_plugin_order(request.order)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if PROGRAM_CONFIG_STORE is None:
        raise RuntimeError('Program config store is not ready')

    PROGRAM_CONFIG_STORE.update_section(
        'colpilot',
        {'plugin_order': ','.join(next_order)},
    )
    plugin_order.clear()
    plugin_order.extend(next_order)
    return list_plugins()


@app.get('/api/plugins/{plugin_id}/status')
def plugin_status(plugin_id: str) -> Any:
    handler = get_plugin_handler(plugin_id)
    status_method = getattr(handler, 'status', None)
    if not callable(status_method):
        raise HTTPException(
            status_code=501,
            detail=f'Plugin status interface is unavailable: {plugin_id}',
        )
    return status_method(enabled_plugins[plugin_id])


@app.post('/api/plugins/{plugin_id}/settings')
def update_plugin_settings(plugin_id: str, settings: dict[str, object]) -> Any:
    handler = get_plugin_handler(plugin_id)
    settings_method = getattr(handler, 'update_settings', None)
    if not callable(settings_method):
        raise HTTPException(
            status_code=501,
            detail=f'Plugin settings interface is unavailable: {plugin_id}',
        )
    try:
        settings_method(settings, enabled_plugins[plugin_id])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return handler.status(enabled_plugins[plugin_id])


@app.post('/api/plugins/{plugin_id}/open-output-directory')
def open_plugin_output_directory(plugin_id: str) -> Any:
    get_plugin_definition(plugin_id)
    if not enabled_plugins[plugin_id]:
        raise HTTPException(status_code=409, detail=f'Plugin is disabled: {plugin_id}')
    handler = get_plugin_handler(plugin_id)
    open_method = getattr(handler, 'open_output_directory', None)
    if not callable(open_method):
        raise HTTPException(
            status_code=501,
            detail=f'Plugin output directory interface is unavailable: {plugin_id}',
        )
    try:
        return open_method(enabled_plugins[plugin_id])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post('/api/plugins/{plugin_id}/toggle', response_model=PluginDescriptor)
def toggle_plugin(plugin_id: str, request: PluginToggleRequest) -> PluginDescriptor:
    plugin = get_plugin_definition(plugin_id)
    if plugin['tool_type'] == 'continuous':
        handler = get_plugin_handler(plugin_id)
        if request.enabled:
            handler.start()
        else:
            handler.stop()
    enabled_plugins[plugin_id] = request.enabled
    if PROGRAM_CONFIG_STORE is None:
        raise RuntimeError('Program config store is not ready')
    PROGRAM_CONFIG_STORE.update_section(
        'colpilot',
        {f'enabled_{plugin_id}': request.enabled},
    )
    return build_plugin_descriptor(plugin_id)


@app.post('/api/plugins/{plugin_id}/run')
def run_plugin(plugin_id: str, request: PluginRunRequest) -> Any:
    plugin = get_plugin_definition(plugin_id)
    if plugin['tool_type'] != 'on_demand':
        raise HTTPException(
            status_code=409,
            detail=f'Continuous tool cannot be run on demand: {plugin_id}',
        )
    if not enabled_plugins[plugin_id]:
        raise HTTPException(status_code=409, detail=f'Plugin is disabled: {plugin_id}')
    handler = get_plugin_handler(plugin_id)
    run_method = getattr(handler, 'run', None)
    if not callable(run_method):
        raise HTTPException(
            status_code=501,
            detail=f'Plugin run interface is unavailable: {plugin_id}',
        )
    try:
        result = run_method(request.arguments)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {'accepted': True, 'result': result}


@app.post('/api/commands')
def execute_command(request: CommandRequest) -> dict[str, str | bool]:
    server = getattr(app.state, 'server', None)
    if server is None:
        raise RuntimeError('Backend server is not ready')
    server.should_exit = True
    return {'accepted': True, 'command': request.command}


def main() -> None:
    parser = argparse.ArgumentParser(description='Colpilot local backend')
    parser.add_argument('--port', type=int, default=BACKEND_PORT)
    parser.add_argument(
        '--config-path',
        type=Path,
        default=PROJECT_ROOT / 'config.ini',
    )
    arguments = parser.parse_args()
    configure_runtime(arguments.config_path)

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host='127.0.0.1',
            port=arguments.port,
            log_level='warning',
        )
    )
    app.state.server = server
    server.run()


if __name__ == '__main__':
    main()
