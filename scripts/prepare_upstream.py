#!/usr/bin/env python3
"""Copy the pinned upstream; apply checked, Android-only substitutions.

The submodule remains pristine. An incompatible upstream update fails the build
instead of silently producing an app with missing features.
"""
from pathlib import Path
import shutil
import subprocess
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'app/build/generated/python/pikaraoke'
SONG_STORAGE_OVERLAY = ROOT / 'app/src/main/song-storage/pikaraoke'
PHONE_MIC_OVERLAY = ROOT / 'app/src/main/phone-microphones/pikaraoke'
PLAYBACK_PATCH = ROOT / 'app/src/main/android-tv/splash-playback.patch'

# Storage patches are applied first. Phone preference patches below then extend
# the resulting preference manager without duplicating storage validation.
STORAGE_PATCHES = (
    ('karaoke.py',
     'from pikaraoke.lib.queue_manager import QueueManager\nfrom pikaraoke.lib.song_manager import SongManager\n',
     'from pikaraoke.lib.queue_manager import QueueManager\nfrom pikaraoke.lib.song_list import SongList\nfrom pikaraoke.lib.song_manager import SongManager\nfrom pikaraoke.lib.song_storage import PREFERENCE as SONG_STORAGE_PREFERENCE\nfrom pikaraoke.lib.song_storage import (\n    cleanup_journal_path,\n    prune_songs,\n    reconcile_journal,\n)\n'),
    ('karaoke.py',
     '        self.db = KaraokeDatabase()\n        self.song_manager = SongManager(\n',
     '        self.db = KaraokeDatabase()\n        self.song_storage_cleanup = self._prune_song_storage()\n        self.song_manager = SongManager(\n'),
    ('karaoke.py',
     '    def sync_library(self) -> bool:\n',
     '    def _prune_song_storage(self) -> dict[str, int | bool | None]:\n        """Run the configured quota before any manager warms the song library."""\n        journal_path = cleanup_journal_path(get_data_directory(), self.download_path)\n        result = prune_songs(\n            self.download_path,\n            self.preferences.get_or_default(SONG_STORAGE_PREFERENCE),\n            SongList.VALID_EXTENSIONS,\n            journal_path,\n        )\n        try:\n            reconcile_journal(self.download_path, journal_path, self.db)\n        except OSError:\n            result["error"] = True\n            logging.warning("Song storage database reconciliation stopped", exc_info=True)\n        return result\n\n    def sync_library(self) -> bool:\n'),
    ('lib/preference_manager.py',
     'from pikaraoke.lib.get_platform import get_data_directory\n',
     'from pikaraoke.lib.get_platform import get_data_directory\nfrom pikaraoke.lib.song_storage import PREFERENCE as SONG_STORAGE_PREFERENCE\nfrom pikaraoke.lib.song_storage import parse_limit\n'),
    ('lib/preference_manager.py',
     '        "suggestion_name_order": "artist_title",\n',
     '        "suggestion_name_order": "artist_title",\n        "max_song_storage_bytes": 0,\n'),
    ('lib/preference_manager.py',
     '        return self.get(preference, self.DEFAULTS.get(preference))\n',
     '        default = self.DEFAULTS.get(preference)\n        value = self.get(preference, default)\n        if preference == SONG_STORAGE_PREFERENCE:\n            try:\n                return parse_limit(value)\n            except ValueError:\n                logging.warning("Song storage limit is invalid; automatic cleanup is off")\n                return default\n        return value\n'),
    ('lib/preference_manager.py',
     '        logging.debug(f"Changing preference [{section}] << {preference} >> to {val}")\n',
     '        logging.debug(f"Changing preference [{section}] << {preference} >> to {val}")\n        if preference == SONG_STORAGE_PREFERENCE and section == "USERPREFERENCES":\n            try:\n                val = parse_limit(val)\n            except ValueError:\n                return (False, _("Enter a valid storage limit. Use 0 to turn it off."))\n'),
    ('lib/preference_manager.py',
     '                setattr(self._target, pref, self.get(pref, default))\n',
     '                value = (\n                    self.get_or_default(pref)\n                    if pref == SONG_STORAGE_PREFERENCE\n                    else self.get(pref, default)\n                )\n                setattr(self._target, pref, value)\n'),
    ('routes/settings.py',
     '    k = get_karaoke_instance()\n    return render_template(\n',
     '    k = get_karaoke_instance()\n    cleanup = k.song_storage_cleanup\n    song_storage_unmet = cleanup["error"] or (\n        cleanup["limit_bytes"] > 0\n        and cleanup["after_bytes"] is not None\n        and cleanup["after_bytes"] > cleanup["limit_bytes"]\n    )\n    return render_template(\n'),
    ('routes/settings.py',
     '        enable_folder_browsing=k.enable_folder_browsing,\n        score_phrases={\n',
     '        enable_folder_browsing=k.enable_folder_browsing,\n        max_song_storage_bytes=k.max_song_storage_bytes,\n        song_storage_unmet=song_storage_unmet,\n        score_phrases={\n'),
    ('templates/settings.html',
     '\t\t\t<hr class="my-0">\n\n\t\t\t{# The song database.',
     '\t\t\t<hr class="my-0">\n\n\t\t\t{% include \'partials/song_storage.html\' %}\n\n\t\t\t{# The song database.'),
)

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


def apply_playback_patch():
    """Apply the Android-only splash source handoff patch with exact context."""
    command = ['git', 'apply', '--directory', 'app/build/generated/python', str(PLAYBACK_PATCH)]
    check = subprocess.run(
        [*command[:2], '--check', *command[2:]], cwd=ROOT, text=True, capture_output=True
    )
    if check.returncode:
        raise RuntimeError(f'Upstream splash adapter conflict:\n{check.stderr.strip()}')
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(ROOT / 'upstream/pikaraoke', DEST, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(SONG_STORAGE_OVERLAY, DEST, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for relative, old, new in STORAGE_PATCHES:
        replace(DEST / relative, old, new)
    shutil.copytree(PHONE_MIC_OVERLAY, DEST, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for relative, old, new in PHONE_MIC_PATCHES:
        replace(DEST / relative, old, new)
    apply_playback_patch()
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
