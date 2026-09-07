<!-- "MOF 10 SEGUNDOS", paso 1 de 2: la IMAGEN, que se hace en Flow con la foto
     de la prenda como referencia. El vídeo sale después en Omni a partir de
     ella (ver `prompt_mof10_guion.md`).

     El texto de HOMBRE es el suyo, literal de su web. El de mujer se deriva
     cambiando los marcadores `{{...}}` (valores en `config.SEXOS_MOF10`),
     igual que hace él en el Nicho Zapatos. Si algún día publica la versión de
     mujer, se pega encima y se quitan los marcadores de esas piezas. -->

{
  "subject": {
    "description": "A random attractive young {{PERSONA}} between 18 and 35 years old, standing inside a bright modern bedroom or dressing room. {{EL}} is taking a casual UGC-style selfie with one arm fully extended toward the camera, creating the clear perspective of a handheld front-facing smartphone photo. {{SU}} body is framed from the top of {{SU_MIN}} head to approximately mid-thigh. {{EL}} faces the camera directly with a relaxed posture and a slight natural lean.",
    "age": "random between 18-35",
    "expression": "natural, confident and friendly expression, relaxed lips or a subtle smile, looking directly into the camera",
    "hair_color": "any natural color",
    "style": "any natural {{GENERO_ADJ}} hairstyle"
  },
  "clothing": {
    "source": "The {{GENERO_SUJETO}} subject MUST wear exactly the clothing shown in the provided clothing reference image.",
    "instructions": [
      "IMPORTANT: Use the attached clothing reference image exclusively to reproduce the outfit.",
      "Replicate the outfit from the clothing reference image with absolute accuracy.",
      "Adapt the referenced clothing naturally to a {{GENERO_SUJETO}} body without changing its original design.",
      "Match every garment, color, fabric, texture, stitching, fit, proportions, patterns, logos and visible detail.",
      "Do not reinterpret, redesign, replace, simplify or omit any part of the outfit.",
      "The clothing must look naturally worn while preserving every visual characteristic of the reference.",
      "Do not use the clothing worn by the person in the composition reference image.",
      "The composition reference image defines only the pose, framing, camera perspective, setting and visual style."
    ]
  },
  "face": {
    "makeup": "{{MAQUILLAJE}}",
    "details": "{{CARA}}"
  },
  "accessories": {
    "jewelry": "minimal {{GENERO_ADJ}} accessories, such as a discreet watch, bracelet or necklace, or none"
  },
  "device": {
    "type": "front-facing smartphone camera",
    "position": "held in one fully extended hand directly in front of the subject and slightly above chest level",
    "visibility": "the smartphone remains outside the frame; the extended forearm enters prominently from the lower-left foreground, matching the reference composition"
  },
  "pose": {
    "stance": "standing naturally and facing the camera, torso slightly angled while keeping the front of the outfit clearly visible",
    "arms": "one arm fully extended toward the lens to take the selfie; the other arm rests naturally beside the body",
    "body_orientation": "front-facing, without turning around or showing the back of the clothing"
  },
  "photography": {
    "camera_style": "authentic handheld UGC selfie captured with a front-facing iPhone camera",
    "angle": "close handheld selfie perspective from slightly above chest height, with mild wide-angle distortion caused by the extended arm",
    "shot_type": "vertical medium three-quarter shot, framed from the top of the head to approximately mid-thigh",
    "composition": "the {{PERSONA}} occupies most of the vertical frame; {{SU_MIN}} extended forearm appears large in the lower-left foreground; the outfit remains centered and clearly visible",
    "aspect_ratio": "9:16 vertical",
    "focus": "sharp natural focus on the {{PERSONA}} and clothing, with a softly detailed background",
    "quality": "ultra-photorealistic iPhone UGC quality, realistic skin and fabric textures, subtle smartphone processing and no artificial studio finish"
  },
  "background": {
    "setting": "bright, tidy and modern bedroom or dressing room with soft neutral colors",
    "elements": "large windows with translucent curtains, a white chest of drawers, pale walls and a small decorative plant, arranged similarly to the composition reference",
    "restrictions": "no other people, no mirrors showing unwanted reflections and no distracting objects"
  },
  "lighting": {
    "type": "soft natural daylight entering through large windows",
    "direction": "diffused frontal and side lighting",
    "effect": "bright and flattering illumination with soft shadows, realistic skin tones and clearly visible clothing details"
  },
  "atmosphere": {
    "mood": "casual, confident, fresh and authentic {{GENERO_SUJETO}} fashion UGC",
    "restrictions": "no filters, no beauty effects, no cinematic grading, no borders, no interface elements, no labels, no logos added by the generator and no text overlays"
  }
}
