"""Recorta la hoja de sprites del guía (hecha con Gemini), quita el fondo magenta y alinea las poses.

Uso: python recursos/guia/recortar_guia.py  -> genera interfaz/web/img/guia/*.png
"""
from pathlib import Path
import numpy as np
from PIL import Image

HOJA = Path(__file__).with_name("hoja_gemini.webp")
DESTINO = Path(__file__).resolve().parents[2] / "interfaz" / "web" / "img" / "guia"
NOMBRES = [
    "reposo", "parpadeo", "saludo_mano", "saludo_visera",
    "senala_derecha", "_senala_derecha_2", "senala_arriba", "senala_abajo",
    "celebra", "pulgar", "pensando", "partitura",
]


def magentez(a):
    """0 = nada de magenta, 1 = magenta puro (fondo)."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = np.minimum(r, b) - g                        # el magenta tiene R y B altos y G bajo
    return np.clip((m - 40) / 140.0, 0, 1)


def quitar_fondo(rgb):
    a = rgb.astype(float)
    mag = magentez(a)
    alfa = np.where(mag > 0.85, 0.0, 1.0)
    # Bordes mezclados con el fondo (morados): se quedan opacos pero sin tinte magenta,
    # oscurecidos hacia el color del contorno, como en pixel art.
    borde = (mag > 0.15) & (mag <= 0.85)
    oscuro = np.stack([a[..., 1]] * 3, axis=-1) * 0.6   # usa el canal verde (sin magenta) como luminosidad
    a[borde] = oscuro[borde]
    out = np.dstack([np.clip(a, 0, 255), alfa * 255]).astype(np.uint8)
    return out


def tramos(v, umbral):
    t, dentro = [], False
    for i, x in enumerate(v):
        if x > umbral and not dentro:
            ini, dentro = i, True
        elif x <= umbral and dentro:
            t.append((ini, i)); dentro = False
    if dentro:
        t.append((ini, len(v)))
    return t


def main():
    rgba = quitar_fondo(np.asarray(Image.open(HOJA).convert("RGB")))
    alfa = rgba[..., 3] > 0
    poses = []
    for (f0, f1) in tramos(alfa.sum(1), 3):
        cols = tramos(alfa[f0:f1].sum(0), 1)
        # unir huecos pequeños dentro de un mismo personaje (p. ej. el brazo que señala)
        unidos = []
        for c in cols:
            if unidos and c[0] - unidos[-1][1] < 25:
                unidos[-1] = (unidos[-1][0], c[1])
            else:
                unidos.append(c)
        for (c0, c1) in unidos:
            trozo = rgba[f0:f1, c0:c1]
            ys, xs = np.nonzero(trozo[..., 3])
            trozo = trozo[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            poses.append(trozo)
    assert len(poses) == 12, f"se esperaban 12 poses y hay {len(poses)}"

    # Ancla: centro horizontal de la gorra (parte alta) y pies (parte baja)
    def ancla(p):
        h = p.shape[0]
        alto = p[: int(h * 0.15), :, 3] > 0
        xs = np.nonzero(alto)[1]
        return (xs.min() + xs.max()) / 2.0

    anclas = [ancla(p) for p in poses]
    izq = max(a for a in anclas)
    der = max(p.shape[1] - a for p, a in zip(poses, anclas))
    alto = max(p.shape[0] for p in poses)
    medio = int(max(izq, der)) + 4
    ancho_lienzo = 2 * medio
    alto_lienzo = alto + 4

    DESTINO.mkdir(parents=True, exist_ok=True)
    imagenes = {}
    for nombre, p, a in zip(NOMBRES, poses, anclas):
        lienzo = Image.new("RGBA", (ancho_lienzo, alto_lienzo), (0, 0, 0, 0))
        x = int(round(medio - a)); y = alto_lienzo - 2 - p.shape[0]
        lienzo.paste(Image.fromarray(p), (x, y))
        imagenes[nombre] = lienzo
    # La pose 6 de Gemini señala al mismo lado que la 5: la izquierda es su espejo
    imagenes["senala_izquierda"] = imagenes.pop("_senala_derecha_2").transpose(Image.FLIP_LEFT_RIGHT)
    for nombre, img in imagenes.items():
        img.save(DESTINO / f"{nombre}.png", optimize=True)
    print("lienzo", ancho_lienzo, "x", alto_lienzo, "->", sorted(imagenes))

    # Vista previa sobre el fondo oscuro de la app
    orden = ["reposo", "parpadeo", "saludo_mano", "saludo_visera", "senala_izquierda", "senala_derecha",
             "senala_arriba", "senala_abajo", "celebra", "pulgar", "pensando", "partitura"]
    prev = Image.new("RGBA", (ancho_lienzo * 6, alto_lienzo * 2), (20, 20, 22, 255))
    for i, n in enumerate(orden):
        prev.alpha_composite(imagenes[n], ((i % 6) * ancho_lienzo, (i // 6) * alto_lienzo))
    prev.convert("RGB").save(Path(__file__).with_name("vista_previa.png"))


if __name__ == "__main__":
    main()
