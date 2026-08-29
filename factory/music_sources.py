from __future__ import annotations

from typing import Any


FLOW_MUSIC_PROMPTS: tuple[dict[str, str], ...] = (
    {"name": "Midnight Rhodes", "prompt": "Instrumental lo-fi chill, warm Rhodes chords, soft boom-bap drums, round bass, subtle vinyl texture, rainy late-night mood, 72 BPM, calm and introspective, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Rainy Felt Piano", "prompt": "Instrumental calm lo-fi, intimate felt piano, brushed drums, gentle upright bass, soft rain ambience outside a window, 68 BPM, sleep and reading mood, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Quiet Nylon Night", "prompt": "Instrumental chill lo-fi, mellow nylon guitar, dusty percussion, deep soft bass, sparse electric piano accents, blue-hour city mood, 74 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Vibraphone After Hours", "prompt": "Instrumental nocturnal lo-fi jazz, gentle vibraphone melody, muted drums, warm Rhodes and upright bass, rainy empty cafe atmosphere, 76 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Weightless Window", "prompt": "Instrumental ambient lo-fi, slowly evolving analog pads, soft tape texture, distant electric piano, no drums, peaceful night skyline in the rain, 3 to 4 minutes, seamless loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Cassette Soul", "prompt": "Instrumental soulful lo-fi, warm electric piano, restrained pocket drums, rounded bass, cassette saturation, nostalgic rainy street mood, 70 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Neon Study", "prompt": "Instrumental modern chillhop, clean Rhodes voicings, crisp but soft drums, melodic bass and airy synth details, focused night study mood, 78 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Cafe Wurlitzer", "prompt": "Instrumental cozy lo-fi, mellow Wurlitzer chords, brushed snare, soft bass and tiny guitar harmonics, warm cafe during nighttime rain, 73 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Deep Sleep Piano", "prompt": "Instrumental sleep lo-fi, very soft felt piano, low warm drones, delicate tape noise, no drums, slow peaceful harmony, 3 to 4 minutes, seamless loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Emerald City Night", "prompt": "Instrumental cinematic lo-fi, dark emerald analog pads, sparse Rhodes, minimal soft kick and rim percussion, lonely high-rise city at 3 AM, 69 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Organic Rain Garden", "prompt": "Instrumental organic lo-fi, gentle kalimba, warm piano, hand percussion, soft sub bass and natural room texture, contemplative rainy garden mood, 75 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
    {"name": "Last Train Home", "prompt": "Instrumental late-night lo-fi, muted electric guitar, Rhodes, train-like brushed rhythm and deep mellow bass, nostalgic final-train atmosphere, 71 BPM, 3 to 4 minutes, loop-friendly ending, no vocals, no samples, no artist imitation."},
)


def flow_music_guide() -> dict[str, Any]:
    return {
        "provider": "Google Flow Music · Lyria",
        "mode": "manual_download_safe",
        "reason": "A geração, a conta e o download permanecem sob controle do usuário; a fábrica automatiza a validação, rotação e montagem local.",
        "workflow": [
            "Gerar uma faixa instrumental no Flow Music usando um dos prompts.",
            "Ouvir e baixar somente o arquivo de áudio.",
            "Importar o arquivo ou a pasta na Biblioteca e confirmar os direitos de uso.",
            "A fábrica normaliza, alterna as faixas e combina música e capa localmente.",
        ],
        "prompts": list(FLOW_MUSIC_PROMPTS),
    }
