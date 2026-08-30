from __future__ import annotations

from typing import Any


FLOW_MUSIC_PROMPTS: tuple[dict[str, str], ...] = (
    {"name": "Velvet Platform", "prompt": "Instrumental jazz-hop at 78 BPM in D minor, warm Rhodes chords, upright bass and dry brushed drums with gentle swing. Distinct A-B-A structure, restrained melodic improvisation, late-night train-platform mood. No rain sounds, no vinyl crackle, no vocals, no long ambient pad intro."},
    {"name": "Coastal Nylon", "prompt": "Instrumental lo-fi bossa at 84 BPM in A minor, intimate nylon-string guitar, soft shaker, rim clicks and rounded acoustic bass. Syncopated Brazilian harmony, calm seaside dusk mood, loop-friendly ending. No piano, no synthesizer pads, no rain, no vocals."},
    {"name": "Neon Afterimage", "prompt": "Instrumental downtempo synthwave at 74 BPM in F-sharp minor, analog arpeggio, deep electronic bass, gated snare used sparingly and a glassy lead motif. Dark neon city mood with a clear evolving middle section. No piano, no boom-bap drums, no environmental effects, no vocals."},
    {"name": "Paper Lantern Steps", "prompt": "Instrumental Japanese-inspired chillhop at 72 BPM, koto plucks as the lead, shakuhachi-like breathy texture, soft boom-bap drums and minimal sub bass. Pentatonic melody, warm nocturnal alley mood. No piano, no jazz chords, no rain audio, no vocals."},
    {"name": "Slow Orbit", "prompt": "Beatless instrumental ambient at 50 BPM in C minor, evolving granular synthesizer, bowed glass harmonics and a very low drone. Spacious cosmic arc with gradual timbral movement and no repeated four-chord loop. No drums, no piano, no tape hiss, no vocals."},
    {"name": "Moss on the Window", "prompt": "Instrumental acoustic lo-fi folk at 66 BPM in G minor, fingerpicked steel-string guitar, soft cello counterline, muted hand percussion and natural room tone. Reflective forest-cabin mood with a distinct bridge. No keyboards, no electronic drums, no rain sounds, no vocals."},
    {"name": "Blue Hour Dub", "prompt": "Instrumental ambient dub at 70 BPM, deep syncopated bass, sparse chord stabs, tape-delay echoes and minimal kick pattern. Calm blue-hour city mood, negative space and slowly changing effects. No piano melody, no jazz swing, no rain, no vocals."},
    {"name": "Porcelain Memory", "prompt": "Instrumental chamber lo-fi at 58 BPM in E minor, intimate felt piano answered by solo cello and quiet viola, no drum kit. Through-composed three-part form rather than a repeating beat, restrained and tender. No synthesizer pads, no vinyl noise, no rain, no vocals."},
    {"name": "Soft Geometry", "prompt": "Instrumental minimal chill at 80 BPM in B-flat minor, marimba lead, electric bass harmonics and precise soft percussion with an asymmetrical five-bar phrase. Focused modern studio mood. No piano, no guitar, no ambient drone, no rain sounds, no vocals."},
    {"name": "Last Tram Home", "prompt": "Instrumental trip-hop at 68 BPM in C-sharp minor, muted electric guitar motif, dusty breakbeat, warm sub bass and occasional vibraphone accents. Cinematic but understated, with a breakdown halfway through. No Rhodes, no four-on-the-floor beat, no rain audio, no vocals."},
    {"name": "Unsent Letter", "prompt": "Instrumental dream-pop lo-fi at 76 BPM in A major with bittersweet modal harmony, chorus-soaked electric guitar, melodic fretless bass and soft live drums. Gentle rising second section and resolved outro. No piano, no vinyl crackle, no environmental sounds, no vocals."},
    {"name": "Rooms Without Clocks", "prompt": "Instrumental modern classical ambient at 55 BPM, prepared piano used only as sparse punctuation, clarinet choir and subtle bowed vibraphone. Free-flowing form with long harmonic changes and no beat. No lo-fi drum loop, no rain, no tape hiss, no vocals."},
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
