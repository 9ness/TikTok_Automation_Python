<!-- "Zapatillas Vista Sentado 20s (Moda Mujer · aleatorios)", paso 1 de 2: la IMAGEN. Texto literal de su web
     (ttshopaiproapp.com, 30 sep 2026). Su nota: Paso 1: Enviar imagen del producto a Flow. Crear 2 imágenes y pasarlas a
     video. El movimiento os lo devuelve en el prompt número 2. Hay que crear voz independiente en Fish por la duración de 20
     segundos de video, ya que Onmi solo genera videos de 10 segundos. Eliminar las voces generadas por Onmi en los videos.
     El paso 2 es EL MISMO que el de Zapatillas Vista POV 20s: el gancho de punto de dolor del POV BOF Largo
     (`nicho_pov_bof_largo/prompts/guion_dolor.md`). -->

{
  "subject": {
    "description": "A completely random adult woman sitting naturally, photographed from a low front angle. Only her feminine lower body is visible, from approximately the knees down. She is wearing the footwear shown in the provided product reference image.",
    "gender": "female only",
    "age": "random adult woman between 18 and 40",
    "skin_tone": "any random natural skin tone",
    "body_type": "any random female body type",
    "legs": "clearly feminine adult legs with natural female anatomy, proportions, shape and realistic skin texture"
  },
  "product": {
    "source": "The woman MUST wear exactly the footwear shown in the provided reference image.",
    "instructions": [
      "Use the provided reference image exclusively as the footwear reference.",
      "Replicate its exact design, shape, colors, materials, stitching, sole, laces, branding and proportions.",
      "Show the complete matching pair naturally worn on both female feet.",
      "Do not redesign, recolor, simplify, deform, replace or add details."
    ]
  },
  "pose": {
    "position": "the woman is sitting naturally on a random seat with her knees bent",
    "legs": "two clearly feminine legs, slightly separated in a relaxed and natural posture",
    "feet": "both female feet resting naturally on the floor, with one foot slightly closer to the camera",
    "visibility": "both shoes and both feminine legs must remain clearly visible and unobstructed from approximately the knees down",
    "restriction": "Do not show the woman’s face, torso or upper body."
  },
  "clothing": {
    "instructions": "Generate random feminine casual trousers, jeans, leggings, a skirt or shorts, together with random feminine socks that look natural with the footwear. The clothing must change in every generation and must not cover or obstruct the shoes."
  },
  "photography": {
    "style": "realistic casual smartphone UGC photograph",
    "angle": "low frontal angle focused on the woman’s legs, feet and footwear",
    "framing": "vertical close shot showing only the female lower body from approximately the knees to the floor",
    "aspect_ratio": "9:16 vertical",
    "focus": "sharp focus on the referenced footwear and feminine legs, with natural background depth",
    "quality": "ultra-photorealistic and authentic smartphone quality"
  },
  "background": {
    "setting": "a completely random real-world indoor or outdoor environment with a suitable place for the woman to sit",
    "examples": [
      "bedroom",
      "living room",
      "hallway",
      "dressing room",
      "bench",
      "waiting area",
      "terrace"
    ],
    "instructions": [
      "Choose a different coherent environment in every generation.",
      "The environment, seat, floor, feminine clothing and woman must always be random.",
      "Do not reproduce the room shown in the example image.",
      "Do not allow background objects to obstruct the footwear or the woman’s legs."
    ]
  },
  "lighting": {
    "type": "natural realistic lighting appropriate to the random environment",
    "effect": "authentic shadows, realistic skin tones, natural exposure and an authentic smartphone appearance"
  },
  "restrictions": [
    "The visible legs and feet must always belong to one adult woman.",
    "Never generate masculine, male-presenting or androgynous legs.",
    "Show exactly two feminine legs and exactly two female feet.",
    "Do not show extra legs, feet, hands or other people.",
    "Do not generate additional shoes outside the matching pair being worn.",
    "Do not show the woman’s face, torso or upper body.",
    "Do not add text, subtitles, interface elements, watermarks or graphics.",
    "Do not create a polished studio or professional advertising appearance."
  ],
  "randomization": "The adult woman, feminine legs, clothing, socks, environment, seat and lighting must change in every generation. Only the referenced footwear remains fixed."
}
