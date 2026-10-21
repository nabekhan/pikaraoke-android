#!/usr/bin/env python3
"""Copy the pinned upstream; apply checked, Android-only substitutions.

The submodule remains pristine. An incompatible upstream update fails the build
instead of silently producing an app with missing features.
"""
from pathlib import Path
import shutil
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'app/build/generated/python/pikaraoke'
PHONE_MIC_OVERLAY = ROOT / 'app/src/main/phone-microphones/pikaraoke'

# Each patch is deliberately limited to the phone feature's shared integration
# point. replace() below refuses missing or duplicated anchors when upstream
# changes one of these files.
PHONE_MIC_PATCHES = (
    ('lib/preference_manager.py', 'import shutil\nfrom typing import Any\n',
     'import shutil\nimport threading\nfrom typing import Any\n'),
    ('lib/preference_manager.py', '        "mic_settings": "{}",\n',
     '        "mic_settings": "{}",\n        "max_phone_mics": 2,\n'),
    ('lib/preference_manager.py', '        self._target = target  # Object to sync attributes on\n',
     '        self._target = target  # Object to sync attributes on\n        self.mutation_lock = threading.RLock()\n'),
    ('lib/preference_manager.py',
     '        value = self.get(preference, default)\n        if preference == SONG_STORAGE_PREFERENCE:\n',
     '        value = self.get(preference, default)\n        if preference == "max_phone_mics" and (type(value) is not int or not 1 <= value <= 4):\n            return default\n        if preference == SONG_STORAGE_PREFERENCE:\n'),
    ('lib/preference_manager.py',
     '        logging.debug(f"Changing preference [{section}] << {preference} >> to {val}")\n',
     '        with self.mutation_lock:\n            return self._set(preference, val, section)\n\n    def _set(self, preference: str, val: Any, section: str) -> tuple[bool, str]:\n        """Write a preference while the caller holds the mutation lock."""\n        logging.debug(f"Changing preference [{section}] << {preference} >> to {val}")\n        if preference == "max_phone_mics" and section == "USERPREFERENCES":\n            val = self._convert_value(val)\n            if type(val) is not int or not 1 <= val <= 4:\n                return (False, _("Choose 1 to 4 phone mics."))\n'),
    ('lib/preference_manager.py',
     '        try:\n            self._config_obj.read(self.config_file_path, encoding="utf-8")\n\n            if self._config_obj.has_section("USERPREFERENCES"):\n',
     '        with self.mutation_lock:\n            return self._clear()\n\n    def _clear(self) -> tuple[bool, str]:\n        """Clear persisted user preferences under the mutation lock."""\n        try:\n            self._config_obj.read(self.config_file_path, encoding="utf-8")\n\n            if self._config_obj.has_section("USERPREFERENCES"):\n'),
    ('lib/preference_manager.py',
     '                value = (\n                    self.get_or_default(pref)\n                    if pref == SONG_STORAGE_PREFERENCE\n                    else self.get(pref, default)\n                )\n',
     '                value = (\n                    self.get_or_default(pref)\n                    if pref in ("max_phone_mics", SONG_STORAGE_PREFERENCE)\n                    else self.get(pref, default)\n                )\n'),
    ('lib/preference_manager.py',
     '        success, message = self.clear()\n        if success and self._target is not None:\n            for pref, default in self.DEFAULTS.items():\n                setattr(self._target, pref, default)\n        return success, message\n',
     '        with self.mutation_lock:\n            success, message = self.clear()\n            if success and self._target is not None:\n                for pref, default in self.DEFAULTS.items():\n                    setattr(self._target, pref, default)\n            return success, message\n'),
    ('routes/settings.py',
     '        mic_available=k.sound_manager.available,\n',
     '        mic_available=k.sound_manager.available,\n        max_phone_mics=k.preferences.get_or_default("max_phone_mics"),\n'),
    ('templates/base.html',
     '          <span class="is-truncated">{% trans %}Join in{% endtrans %}</span>\n        </a>\n        <a role="button" class="navbar-burger"',
     '          <span class="is-truncated">{% trans %}Join in{% endtrans %}</span>\n        </a>\n        {% if phone_mics_available|default(false) %}\n        <a id="phone-mic" class="navbar-item no-spa" href="{{ base_path }}/mic" aria-label="Phone microphone" title="Phone microphone">\n          <i class="icon icon-mic-1" aria-hidden="true"></i>\n        </a>\n        {% endif %}\n        <a role="button" class="navbar-burger"'),
    ('templates/settings.html',
     '\t\t\t\t</label>\n\t\t\t\t{% if mic_passthrough_enabled %}\n',
     '\t\t\t\t</label>\n\t\t\t\t{% if phone_mics_available %}\n\t\t\t\t<div class="panel-block px-5 py-3 is-justify-content-space-between">\n\t\t\t\t\t<label for="pref-max-phone-mics">{% trans %}Phone mic limit{% endtrans %}</label>\n\t\t\t\t\t<div class="select is-flex-shrink-0 ml-4">\n\t\t\t\t\t\t<select id="pref-max-phone-mics" class="user-preference-input" data-pref="max_phone_mics" data-start-value="{{ max_phone_mics }}">\n\t\t\t\t\t\t\t{% for count in range(1, 5) %}<option value="{{ count }}" {% if count == max_phone_mics %}selected{% endif %}>{{ count }}</option>{% endfor %}\n\t\t\t\t\t\t</select>\n\t\t\t\t\t</div>\n\t\t\t\t</div>\n\t\t\t\t{% endif %}\n\t\t\t\t{% if mic_passthrough_enabled %}\n'),
)


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Upstream adapter conflict in {path.name}: {old!r}')
    path.write_text(text.replace(old, new))


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(ROOT / 'upstream/pikaraoke', DEST, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(PHONE_MIC_OVERLAY, DEST, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for relative, old, new in PHONE_MIC_PATCHES:
        replace(DEST / relative, old, new)
    # Upstream's package import eagerly binds platform functions in Karaoke.
    # Defer that import until the Android adapters have been installed.
    replace(DEST / '__init__.py', 'from pikaraoke.karaoke import Karaoke\n', '')
    replace(DEST / '__init__.py', '    Karaoke.__name__,', '    "Karaoke",')
    with (DEST / '__init__.py').open('a') as out:
        out.write('\n\ndef __getattr__(name):\n'
                  '    if name == "Karaoke":\n'
                  '        from pikaraoke.karaoke import Karaoke\n'
                  '        return Karaoke\n'
                  '    raise AttributeError(name)\n')
    replace(DEST / 'app.py', 'from gevent import monkey, spawn\n\nmonkey.patch_all()',
            'from android_runtime.compat import spawn')
    replace(DEST / 'app.py', 'from gevent.pywsgi import WSGIServer',
            'from android_runtime.compat import WSGIServer')
    replace(DEST / 'app.py', 'async_mode="gevent"', 'async_mode="threading"')
    replace(DEST / 'lib/download_manager.py', 'from gevent import Greenlet, spawn',
            'from android_runtime.compat import Greenlet, spawn')
    replace(DEST / 'templates/base.html', '</head>',
            '<script defer src="{{ url_for(\'static\', filename=\'android-tv.js\') }}"></script>\n</head>')
    shutil.copyfile(ROOT / 'app/src/main/assets/android-tv.js', DEST / 'static/android-tv.js')
    for path in DEST.rglob('*.po'):
        with path.open('rb') as inp, path.with_suffix('.mo').open('wb') as out:
            write_mo(out, read_po(inp))
    print('Prepared pinned PiKaraoke sources and translations')


if __name__ == '__main__':
    main()
