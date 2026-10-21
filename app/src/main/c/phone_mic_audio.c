#include <aaudio/AAudio.h>
#include <jni.h>
#include <stddef.h>
#include <stdint.h>
#include <time.h>

static AAudioStream *stream(jlong handle) {
    return (AAudioStream *)(intptr_t)handle;
}

JNIEXPORT jlong JNICALL Java_org_pikaraoke_tv_PhoneMicPlayback_nativeOpen(
        JNIEnv *env, jclass type, jint device) {
    (void)env; (void)type;
    AAudioStreamBuilder *builder = NULL;
    AAudioStream *output = NULL;
    if (AAudio_createStreamBuilder(&builder) < 0) return 0;
    AAudioStreamBuilder_setDeviceId(builder, device);
    AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_OUTPUT);
    AAudioStreamBuilder_setSampleRate(builder, 48000);
    AAudioStreamBuilder_setChannelCount(builder, 2);
    AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_PCM_I16);
    AAudioStreamBuilder_setSharingMode(builder, AAUDIO_SHARING_MODE_SHARED);
    AAudioStreamBuilder_setPerformanceMode(builder, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY);
    aaudio_result_t result = AAudioStreamBuilder_openStream(builder, &output);
    AAudioStreamBuilder_delete(builder);
    if (result < 0) return 0;
    // Keep the selected TV output and allow the backing track to play too.
    // Reject a fallback route or format instead of silently playing elsewhere.
    if (AAudioStream_getDeviceId(output) != device
            || AAudioStream_getSampleRate(output) != 48000
            || AAudioStream_getChannelCount(output) != 2
            || AAudioStream_getFormat(output) != AAUDIO_FORMAT_PCM_I16
            || AAudioStream_getSharingMode(output) != AAUDIO_SHARING_MODE_SHARED
            || AAudioStream_getPerformanceMode(output) != AAUDIO_PERFORMANCE_MODE_LOW_LATENCY) {
        AAudioStream_close(output); return 0;
    }
    int burst = AAudioStream_getFramesPerBurst(output);
    if (burst <= 0 || AAudioStream_setBufferSizeInFrames(output, burst * 2) < 0
            || AAudioStream_requestStart(output) < 0) {
        AAudioStream_close(output); return 0;
    }
    return (jlong)(intptr_t)output;
}

JNIEXPORT jint JNICALL Java_org_pikaraoke_tv_PhoneMicPlayback_nativeWrite(
        JNIEnv *env, jclass type, jlong handle, jshortArray source, jint offset, jint count) {
    (void)type;
    if (!handle || count < 1 || count > 240 || offset < 0
            || offset > (*env)->GetArrayLength(env, source) - count) return AAUDIO_ERROR_ILLEGAL_ARGUMENT;
    AAudioStream *output = stream(handle);
    // Some implementations accept nonblocking writes up to capacity despite a
    // smaller requested buffer. Keep monitoring close to the endpoint clock.
    int64_t pending = AAudioStream_getFramesWritten(output) - AAudioStream_getFramesRead(output);
    if (pending < 0) pending = 0;
    int64_t room = AAudioStream_getBufferSizeInFrames(output) - pending;
    if (room <= 0) return 0;
    if (room < count) count = (int)room;
    jshort mono[240], stereo[480];
    (*env)->GetShortArrayRegion(env, source, offset, count, mono);
    if ((*env)->ExceptionCheck(env)) return AAUDIO_ERROR_ILLEGAL_ARGUMENT;
    for (int i = 0; i < count; i++) stereo[i * 2] = stereo[i * 2 + 1] = mono[i];
    aaudio_result_t result = AAudioStream_write(output, stereo, count, 0);
    return result == AAUDIO_ERROR_WOULD_BLOCK || result == AAUDIO_ERROR_TIMEOUT ? 0 : result;
}

JNIEXPORT void JNICALL Java_org_pikaraoke_tv_PhoneMicPlayback_nativeInfo(
        JNIEnv *env, jclass type, jlong handle, jlongArray result) {
    (void)type;
    if (!handle || (*env)->GetArrayLength(env, result) < 9) return;
    AAudioStream *output = stream(handle);
    int64_t position = 0, nanos = 0;
    int timestamp = AAudioStream_getTimestamp(output, CLOCK_MONOTONIC, &position, &nanos);
    jlong values[9] = {AAudioStream_getFramesRead(output), AAudioStream_getBufferSizeInFrames(output),
        AAudioStream_getBufferCapacityInFrames(output), AAudioStream_getXRunCount(output),
        AAudioStream_getFramesPerBurst(output), AAudioStream_getFramesWritten(output),
        position, nanos, timestamp};
    (*env)->SetLongArrayRegion(env, result, 0, 9, values);
}

JNIEXPORT void JNICALL Java_org_pikaraoke_tv_PhoneMicPlayback_nativeSetBuffer(
        JNIEnv *env, jclass type, jlong handle, jint frames) {
    (void)env; (void)type;
    if (handle) AAudioStream_setBufferSizeInFrames(stream(handle), frames);
}

JNIEXPORT void JNICALL Java_org_pikaraoke_tv_PhoneMicPlayback_nativePause(
        JNIEnv *env, jclass type, jlong handle) {
    (void)env; (void)type;
    if (handle) AAudioStream_requestPause(stream(handle));
}

JNIEXPORT void JNICALL Java_org_pikaraoke_tv_PhoneMicPlayback_nativeClose(
        JNIEnv *env, jclass type, jlong handle) {
    (void)env; (void)type;
    if (handle) AAudioStream_close(stream(handle));
}
