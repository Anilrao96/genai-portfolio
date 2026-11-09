"""Bounded PCM input and output. The request path needs no compressed-audio decoder."""
from array import array
import io
import math
import sys
import wave

from .config import MAX_SECONDS, SAMPLE_RATE


class VoiceError(Exception):
    """A safe message for the client."""


def read_wav(payload, *, seconds=MAX_SECONDS):
    try:
        with wave.open(io.BytesIO(payload), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, SAMPLE_RATE):
                raise VoiceError('Use 16 kHz mono PCM16 WAV audio.')
            frames = source.getnframes()
            if not SAMPLE_RATE // 4 <= frames <= SAMPLE_RATE * seconds:
                raise VoiceError(f'Record between a quarter second and {seconds} seconds.')
            pcm = source.readframes(frames)
    except (EOFError, wave.Error) as error:
        raise VoiceError('This recording is not a readable PCM WAV file.') from error
    if len(pcm) != frames * 2:
        raise VoiceError('The WAV recording is incomplete.')
    return pcm


def speech_rms(pcm):
    samples = array('h')
    samples.frombytes(pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    return math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768


def write_wav(pcm):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setparams((1, 2, SAMPLE_RATE, 0, 'NONE', ''))
        output.writeframes(pcm)
    return stream.getvalue()
