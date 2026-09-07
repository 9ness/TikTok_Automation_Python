<!-- "GAFAS EN COCHE 10s" (Moda Hombre, sep 2026), paso 1 de 2: la IMAGEN.

     Es el primer modo del nicho que NO va de ropa: el producto son unas
     gafas, y se las pone un chico sentado en el asiento del conductor de un
     coche parado, haciéndose un selfie. Por eso hace falta el filtro por
     categoría (ver tasks.md): con una camiseta, este prompt no tiene sentido.

     Dos detalles suyos que no están en los demás: prohíbe la ropa VERDE (para
     que no se coma el croma de nada) y pide que la ropa NO combine con el
     producto, para que las gafas destaquen.

     Texto literal suyo. -->

{
  "subject": {
    "description": "A completely random, handsome young man sitting naturally in the driver’s seat of a parked car, taking a casual smartphone selfie. He is wearing the product shown in the provided reference image.",
    "appearance": "handsome, masculine, natural and completely random",
    "age": "random between 20 and 35",
    "face": "a different attractive and realistic male face in every generation, with balanced natural features",
    "hair": "any random length, texture and hairstyle",
    "facial_hair": "random, including clean-shaven, light stubble or a naturally groomed beard",
    "skin_tone": "any random natural skin tone",
    "body_type": "any random healthy body type",
    "expression": "relaxed, confident and naturally attractive"
  },
  "product": {
    "source": "The man MUST wear exactly the product shown in the provided reference image.",
    "instructions": [
      "Use the provided reference image exclusively as the product reference.",
      "Replicate the product’s exact design, shape, frame, lenses, materials, branding, visible details and proportions.",
      "Position the product correctly and naturally on the man’s face.",
      "Do not redesign, recolor, simplify, replace, duplicate or deform the product.",
      "The product is the only fixed visual element."
    ]
  },
  "pose": {
    "position": "sitting naturally in the driver’s seat of a parked car",
    "head": "facing the smartphone camera with a subtle natural turn",
    "body": "relaxed seated posture with the upper torso visible",
    "arms": "one arm naturally extended toward the camera as if holding the smartphone",
    "gaze": "looking confidently toward the smartphone camera"
  },
  "clothing": {
    "style": "completely random casual menswear",
    "instructions": [
      "Generate a different casual outfit in every generation.",
      "Possible garments include plain T-shirts, polo shirts, casual shirts, sweatshirts, hoodies, overshirts and lightweight jackets.",
      "Select the clothing independently from the referenced product.",
      "The clothing must not imitate, match or coordinate with the product.",
      "Do not use green clothing.",
      "The outfit must look realistic, modern and naturally worn.",
      "Do not add accessories that obstruct or compete with the referenced product."
    ]
  },
  "photography": {
    "style": "authentic casual smartphone UGC selfie",
    "angle": "front-facing selfie angle from slightly above chest level",
    "framing": "vertical medium close-up showing the man from approximately the chest upward",
    "aspect_ratio": "9:16 vertical",
    "focus": "natural sharp focus on the man and the referenced product",
    "quality": "ultra-photorealistic, detailed and believable smartphone photography"
  },
  "background": {
    "setting": "the realistic interior of a completely random parked car",
    "instructions": [
      "Generate a different car interior and outdoor background in every generation.",
      "Show natural details such as the seat, headrest, windows, door frame and a small portion of the steering wheel.",
      "The outdoor environment visible through the windows must be random and realistic.",
      "Do not reproduce a specific vehicle, street, city, country or recognizable location.",
      "Keep all background elements natural and incidental."
    ]
  },
  "lighting": {
    "type": "natural daylight entering through the car windows",
    "effect": "realistic skin tones, natural shadows and authentic smartphone exposure"
  },
  "restrictions": [
    "Only one man may appear.",
    "Do not show extra people, faces, hands, arms or duplicated body parts.",
    "Do not duplicate, modify or deform the referenced product.",
    "Do not coordinate the man’s clothing with the product.",
    "Do not generate green clothing.",
    "The car must be stationary and safely parked.",
    "Do not add text, captions, interface elements, watermarks or graphics.",
    "Do not create a polished studio photograph or professional advertising campaign."
  ],
  "randomization": "Generate a different handsome man, face, hair, facial hair, skin tone, casual outfit, car interior and outdoor background every time. Only the product shown in the provided reference image must remain exactly the same."
}
