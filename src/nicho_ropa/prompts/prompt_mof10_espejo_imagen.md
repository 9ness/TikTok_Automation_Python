<!-- "MOF 10 SEGUNDOS · frente a espejo", paso 1 de 2: la IMAGEN, en Flow con
     la foto de la prenda como referencia.

     Se diferencia de la variante "colocando móvil" en el encuadre: aquí es un
     selfie de espejo de CUERPO ENTERO y el escenario es aleatorio, no un
     dormitorio concreto. Texto de hombre literal suyo; el de mujer, derivado
     por los marcadores `{{...}}` (`config.SEXOS_MOF10`). -->

{
  "subject": {
    "description": "A random young {{PERSONA}} of any appearance, with any hair type, length, color, and texture, any body type, any skin tone, any age between 18 and 35, standing barefoot in front of a random type of mirror inside a random indoor setting. {{EL}} is taking a mirror selfie, holding a smartphone in one hand while the other hand is in any natural position. {{SU}} full body is visible from head to toe, standing with any relaxed or natural posture.",
    "age": "random between 18-35",
    "expression": "any natural expression",
    "hair_color": "any color",
    "style": "any hairstyle"
  },
  "clothing": {
    "source": "The subject MUST wear exactly the clothing shown in the provided reference image.",
    "instructions": [
      "IMPORTANT: The clothing MUST be taken directly from the reference image provided by the user.",
      "Replicate the outfit from the reference image with absolute accuracy.",
      "Match every garment, color, fabric, texture, stitching, fit, proportions, accessories, patterns, logos (if present), and small details.",
      "Do not reinterpret, redesign, replace, simplify, or omit any part of the outfit.",
      "The clothing must look naturally worn on the subject while preserving every visual characteristic of the reference.",
      "If multiple reference images are provided, use the outfit from the designated clothing reference image only.",
      "The clothing is the ONLY fixed element of this prompt. Everything else about the subject and background is random."
    ]
  },
  "face": {
    "makeup": "{{CARA_ESPEJO}}"
  },
  "accessories": {
    "jewelry": "any jewelry or none, random and natural (watch, bracelet, necklace, chain, etc.)"
  },
  "device": {
    "type": "smartphone",
    "position": "held in hand, mirror selfie perspective",
    "visibility": "visible in the frame"
  },
  "pose": {
    "stance": "any relaxed standing pose",
    "arms": "one hand holding the phone, the other in any natural position"
  },
  "photography": {
    "camera_style": "mirror selfie, smartphone photography",
    "angle": "straight-on reflection",
    "shot_type": "full body shot",
    "aspect_ratio": "9:16 vertical",
    "focus": "sharp natural focus across entire body",
    "quality": "ultra photorealistic, DSLR quality, extremely sharp, natural skin texture, highly detailed"
  },
  "background": {
    "setting": "any random indoor location",
    "elements": "any random furniture, decor, lighting fixtures, windows, plants, or architectural details, all different each time"
  },
  "lighting": {
    "type": "any natural or artificial lighting mix",
    "direction": "any direction",
    "effect": "balanced cinematic lighting with soft shadows and realistic skin tones"
  },
  "atmosphere": {
    "mood": "any aesthetic lifestyle vibe"
  }
}
