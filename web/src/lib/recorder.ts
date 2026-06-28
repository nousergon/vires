import { useRef, useState } from 'react'
import { api } from './api'

export type VoiceState = 'idle' | 'recording' | 'transcribing'

function friendly(message: string): string {
  if (message.startsWith('503')) return "Voice input isn't enabled."
  return message.replace(/^\d+:\s*/, '')
}

/**
 * Tap-to-record voice input: MediaRecorder captures audio, POSTs the blob to
 * /coach/transcribe (server-side Whisper), and hands back the text. `supported`
 * is false where MediaRecorder/getUserMedia are unavailable (the caller hides the
 * mic) — this is the robust cross-platform path, incl. iOS Safari PWAs where the
 * browser SpeechRecognition API is unreliable.
 */
export function useVoiceInput(onText: (text: string) => void) {
  const [state, setState] = useState<VoiceState>('idle')
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const supported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'

  async function start() {
    setError(null)
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      setError('Microphone permission denied.')
      return
    }
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []
    recorder.ondataavailable = (e) => {
      if (e.data.size) chunksRef.current.push(e.data)
    }
    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop())
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      setState('transcribing')
      try {
        const text = await api.transcribe(blob)
        if (text.trim()) onText(text.trim())
      } catch (e) {
        setError(friendly((e as Error).message))
      } finally {
        setState('idle')
      }
    }
    recorder.start()
    recorderRef.current = recorder
    setState('recording')
  }

  function stop() {
    recorderRef.current?.stop()
  }

  function toggle() {
    if (state === 'recording') stop()
    else if (state === 'idle') void start()
  }

  return { state, error, supported, toggle }
}
