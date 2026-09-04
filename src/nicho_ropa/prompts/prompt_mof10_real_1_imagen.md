<!-- "SITUACIÓN REAL 1", paso 1 de 2: la IMAGEN, que se hace en Flow con la
     foto de la prenda como referencia. El vídeo sale después a partir de ella
     (ver `prompt_mof10_real_1_guion.md`).

     Formato de HOMBRE y solo de hombre: el curso no publica versión de mujer,
     y aquí no se deriva porque la escena entera (dos personas, un piropo al
     outfit) está escrita para él. Texto literal suyo. -->

{
"subject": {
"description": "A random young man standing or slightly posing on a random street. His appearance must be completely random and must not follow any specific physical description. He is being photographed or recorded in a casual UGC (User Generated Content) style, as if another person were using a smartphone. His full body is visible from head to toe in a relaxed and natural posture.",
"appearance": "completely random",
"age": "random between 18 and 35",
"expression": "any natural expression",
"hair": "any random hair type, length, color and style",
"body_type": "any random body type",
"skin_tone": "any random skin tone"
},
"clothing": {
"source": "The subject MUST wear exactly the complete outfit shown in the provided reference image.",
"instructions": [
"IMPORTANT: Use the provided reference image exclusively as the clothing and outfit reference.",
"The young man MUST wear the exact complete outfit from the reference image.",
"Replicate every garment, color, fabric, texture, stitching, fit, cut, proportion, pattern, accessory, logo and visible detail with maximum accuracy.",
"Preserve the exact way each garment fits and is combined in the reference image.",
"Do not reinterpret, redesign, replace, simplify, recolor, add or omit any part of the outfit.",
"The outfit must look naturally worn by the randomly generated subject while retaining every visual characteristic shown in the reference image.",
"If multiple images are provided, use only the image designated as the outfit reference.",
"The outfit is the only fixed visual element. The young man and the street must be different and random in each generation."
]
},
"face": {
"instructions": "Generate a completely random, natural and realistic face without following any specific facial description.",
"facial_hair": "random, including clean-shaven, light stubble or natural facial hair",
"skin_texture": "natural and realistic",
"makeup": "none"
},
"accessories": {
"instructions": "Only include accessories visible as part of the outfit in the reference image. Do not add random accessories that could alter the referenced look."
},
"pose": {
"stance": "any relaxed, natural standing or casual pose",
"arms": "any natural position, such as resting, gesturing or placed in pockets",
"full_body_visibility": "The complete outfit and the subject’s full body must remain clearly visible from head to toe."
},
"photography": {
"camera_style": "Casual smartphone UGC photography or video, as if recorded by a friend or content creator.",
"angle": "any natural handheld angle, without using a fixed composition",
"shot_type": "vertical full-body shot with natural social media framing",
"aspect_ratio": "9:16 vertical",
"camera_movement": "subtle realistic handheld movement and slight natural micro-vibrations",
"focus": "natural sharp focus on the subject with realistic background depth",
"quality": "ultra-photorealistic, highly detailed and authentic smartphone UGC aesthetic",
"restrictions": [
"Do not use an overly polished studio appearance.",
"Do not make the result look like a professional fashion campaign.",
"Keep the framing spontaneous, believable and natural."
]
},
"background": {
"setting": "A completely random real-world street in an unspecified location.",
"instructions": [
"Do not specify or reproduce any exact street, city, country, neighborhood, landmark or recognizable location.",
"Choose a different random street environment for each generation.",
"The street may have random buildings, storefronts, pavements, street furniture, plants, parked vehicles or distant pedestrians.",
"All background elements must appear natural and incidental.",
"Do not let background elements obstruct the subject or the referenced outfit.",
"The randomly selected street must look realistic, coherent and lived-in."
]
},
"lighting": {
"type": "natural lighting appropriate to the randomly generated street and time of day",
"direction": "determined naturally by the selected environment",
"effect": "realistic exposure, natural skin tones, authentic shadows and subtle smartphone auto-exposure variations"
},
"atmosphere": {
"mood": "casual, spontaneous, realistic and authentic UGC lifestyle content",
"randomization": "The young man’s appearance and the street must change randomly in every generation, while the outfit must always remain exactly the same as in the provided reference image."
}
}
