param([string]$VoiceName = 'Microsoft Zira Desktop')
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
$text = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($text) -or $text.Length -gt 500) { throw 'Invalid speech text length.' }
Add-Type -AssemblyName System.Speech
$voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$stream = [System.IO.MemoryStream]::new()
try {
    $voice.SelectVoice($VoiceName)
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,
        [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $voice.SetOutputToAudioStream($stream, $format)
    $voice.Speak($text)
    $voice.SetOutputToNull()
    $bytes = $stream.ToArray()
    [Console]::OpenStandardOutput().Write($bytes, 0, $bytes.Length)
} finally {
    $voice.Dispose()
    $stream.Dispose()
}
