from __future__ import annotations

import re
from typing import Mapping

from backend.user_config import UserConfigStore


HEX_COLOR_PATTERN = re.compile(r'^#[0-9a-fA-F]{6}$')

DEFAULT_APPEARANCE: dict[str, str] = {
    'theme_name': 'midnight',
    'theme_color': '#8b5cf6',
    'background_color': '#0b1020',
    'sidebar_color': '#0d1326',
    'card_color': '#0f172a',
    'card_hover_color': '#1e293b',
    'primary_text_color': '#f8fafc',
    'secondary_text_color': '#8894af',
    'border_color': '#334155',
}

THEME_PRESETS: tuple[dict[str, object], ...] = (
    {
        'id': 'midnight',
        'name': '午夜紫',
        'colors': {
            'theme_color': '#8b5cf6',
            'background_color': '#0b1020',
            'sidebar_color': '#0d1326',
            'card_color': '#0f172a',
            'card_hover_color': '#1e293b',
            'primary_text_color': '#f8fafc',
            'secondary_text_color': '#8894af',
            'border_color': '#334155',
        },
    },
    {
        'id': 'ocean',
        'name': '深海蓝',
        'colors': {
            'theme_color': '#0ea5e9',
            'background_color': '#071521',
            'sidebar_color': '#0a1e2c',
            'card_color': '#0c2a3c',
            'card_hover_color': '#123e53',
            'primary_text_color': '#ecfeff',
            'secondary_text_color': '#8fb3c8',
            'border_color': '#2b5269',
        },
    },
    {
        'id': 'forest',
        'name': '森林绿',
        'colors': {
            'theme_color': '#22c55e',
            'background_color': '#07150e',
            'sidebar_color': '#0b2117',
            'card_color': '#102c1c',
            'card_hover_color': '#183b26',
            'primary_text_color': '#ecfdf5',
            'secondary_text_color': '#9bc4aa',
            'border_color': '#315c42',
        },
    },
    {
        'id': 'rose',
        'name': '玫瑰红',
        'colors': {
            'theme_color': '#f43f5e',
            'background_color': '#180b12',
            'sidebar_color': '#25101a',
            'card_color': '#32131f',
            'card_hover_color': '#4a1b2b',
            'primary_text_color': '#fff1f2',
            'secondary_text_color': '#d0a4b1',
            'border_color': '#64364b',
        },
    },
)

APPEARANCE_KEYS = frozenset(DEFAULT_APPEARANCE)


def read_appearance(config_store: UserConfigStore) -> dict[str, str]:
    raw_values = config_store.read_section('appearance')
    unknown_keys = sorted(set(raw_values) - APPEARANCE_KEYS)
    if unknown_keys:
        raise ValueError(f'外观配置包含未知项目：{", ".join(unknown_keys)}')

    appearance = dict(DEFAULT_APPEARANCE)
    for key, value in raw_values.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f'外观配置项目无效：{key}')
        if key != 'theme_name' and not HEX_COLOR_PATTERN.fullmatch(value):
            raise ValueError(f'外观颜色格式无效：{key}')
        appearance[key] = value
    return appearance


def update_appearance(
    config_store: UserConfigStore,
    values: Mapping[str, object],
) -> dict[str, str]:
    if not values:
        raise ValueError('外观配置更新内容不能为空')
    unknown_keys = sorted(set(values) - APPEARANCE_KEYS)
    if unknown_keys:
        raise ValueError(f'外观配置包含未知项目：{", ".join(unknown_keys)}')

    current = read_appearance(config_store)
    next_values: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f'外观配置项目无效：{key}')
        if key != 'theme_name' and not HEX_COLOR_PATTERN.fullmatch(value):
            raise ValueError(f'外观颜色格式无效：{key}')
        next_values[key] = value

    config_store.update_section('appearance', next_values)
    current.update(next_values)
    return current


def theme_presets() -> list[dict[str, object]]:
    return [
        {
            'id': preset['id'],
            'name': preset['name'],
            'colors': dict(preset['colors']),
        }
        for preset in THEME_PRESETS
    ]
