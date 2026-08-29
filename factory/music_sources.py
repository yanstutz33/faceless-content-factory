from __future__ import annotations

from typing import Any


FLOW_MUSIC_PROMPTS: tuple[dict[str, str], ...] = (
    {"name": "Remembering at 3 A.M.", "prompt": "Extremely slow minimal sad lo-fi instrumental, 58 BPM, minor key, felt piano and distant ambient pads, almost no drums, large spaces between notes, remembering someone at 3 AM, no vocals, no bright melody, no energetic rhythm, no embedded rain sounds."},
    {"name": "Quiet Burnout", "prompt": "Restrained nocturnal lo-fi instrumental, 62 BPM, warm Rhodes, soft analog pad, distant filtered kick and occasional rimshot, quiet loneliness and emotional exhaustion, no swing, no bouncy bass, no catchy hook, no vocals."},
    {"name": "Empty City at Night", "prompt": "Beatless melancholic ambient lo-fi, dark synthesizer pads, subtle tape texture, slow unresolved harmony and a sparse fragile melody, watching an empty city at night, no percussion, no vocals, no environmental sounds."},
    {"name": "Accepting the Distance", "prompt": "Slow sad instrumental, 60 BPM, clean muted guitar, minimal bass, soft room ambience and rare brushed percussion, missing someone but accepting the distance, no cheerful chords, no jazz energy, no vocals."},
    {"name": "Fading Memory", "prompt": "Minimal lo-fi instrumental, 56 BPM, vibraphone, cassette texture and distant warm pads, sparse nostalgic melody like an old memory fading, almost beatless, no bright tones, no vocals, no catchy hook."},
    {"name": "3 A.M. Shadow", "prompt": "Dark late-night ambient instrumental, 54 BPM, deep analog synthesizers, long decays, subtle low-frequency warmth and no drums, lonely, tired and cinematic without drama, no build or climax, no vocals, no sound effects."},
    {"name": "Exhausted Return", "prompt": "Melancholic felt-piano composition, 64 BPM, extremely subtle strings, soft tape saturation, slow minor seventh and add9 chords, coming home emotionally exhausted, no drums, no vocals, no uplifting resolution."},
    {"name": "Echoes in an Empty Room", "prompt": "Extremely calm sleep lo-fi instrumental, 52 BPM, soft electric piano, warm pad, gentle low bass and barely audible filtered percussion, safe, sleepy, distant and slightly sad, no groove, no vocals, no sudden changes."},
    {"name": "Empty City Signal", "prompt": "Minimal 3 AM city lo-fi instrumental, 59 BPM, sparse Rhodes notes, distant synthesizer ambience and very soft irregular percussion, empty city and frozen time, no upbeat beat, no swing, no vocals, no embedded city sounds."},
    {"name": "Fading Harmonics", "prompt": "Slow nostalgic instrumental, 61 BPM, felt piano, muted guitar harmonics, subtle cassette flutter and long silences, memories of someone no longer present, intimate and restrained, no vocals, no hopeful climax."},
    {"name": "3 A.M. Exhaustion", "prompt": "Low-energy melancholic lo-fi instrumental, 57 BPM, dark Rhodes chords, soft analog texture, minimal bass and occasional distant percussion, quiet burnout and tiredness, no catchy melody, no groove, no vocals, no bright instruments."},
    {"name": "Rainless Window at Night", "prompt": "Beatless ambient lo-fi inspired by looking through a rainy window at night without rain or thunder in the audio, slow piano fragments, dark blue pads, tape noise and unresolved minor harmony, extremely calm, lonely, nostalgic and suitable for sleep, no vocals."},
)
FLOW_MUSIC_PROMPTS = tuple({**item, "prompt": f'{item["prompt"]} no artist imitation.'}
                           for item in FLOW_MUSIC_PROMPTS)


def flow_music_guide() -> dict[str, Any]:
    return {
        "provider": "Google Flow Music + Lyria 3",
        "mode": "official_link_bridge_with_api_option",
        "reason": "O Flow Music usa os créditos do Google AI Plus; a Gemini API permanece opcional e cobrada separadamente.",
        "workflow": [
            "Abrir o Flow Music pelo painel e gerar com os créditos do plano Starter.",
            "Baixar as músicas aprovadas e importar o lote na Biblioteca.",
            "Ouvir as faixas na Biblioteca e manter somente as aprovadas.",
            "A fábrica alterna músicas e combina áudio e capa localmente.",
        ],
        "prompts": list(FLOW_MUSIC_PROMPTS),
    }
