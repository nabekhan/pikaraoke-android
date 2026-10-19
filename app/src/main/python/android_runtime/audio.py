"""Use Android AudioRecord/AudioTrack through the upstream microphone API."""
import json


def install_audio_adapter(context):
    from pikaraoke.lib import sound_manager
    from org.pikaraoke.tv import AndroidAudio

    class AndroidSoundManager(sound_manager.SoundManager):
        @property
        def available(self):
            return self._enabled and AndroidAudio.hasPermission(context)

        def enumerate_devices(self):
            self._device_list = json.loads(str(AndroidAudio.devices(context))) if self.available else []
            self._device_index = {d['deviceId']: d for d in self._device_list}
            return self._device_list

        def activate(self, device_id, volume):
            if not self.available:
                return False
            state = self.get_mic_settings_state()
            success = AndroidAudio.activate(context, str(device_id), float(volume),
                                            state['latency_ms'], state['echo_cancel'])
            if success:
                self._active_mics[device_id] = sound_manager._ActiveMic(device_id, None, mic_state=[volume])
            return bool(success)

        def _activate_with_settings(self, device_id, volume, echo_cancel, latency_ms):
            return self.activate(device_id, volume)

        def deactivate(self, device_id):
            AndroidAudio.deactivate(str(device_id))
            self._active_mics.pop(device_id, None)

        def update_volume(self, device_id, volume):
            AndroidAudio.volume(str(device_id), float(volume))
            if device_id in self._active_mics:
                self._active_mics[device_id].mic_state[0] = volume

    sound_manager.SoundManager = AndroidSoundManager
