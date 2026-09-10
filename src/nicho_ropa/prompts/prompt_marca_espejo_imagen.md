<!-- MARCA PERSONAL · Frente a Espejo Multi Escena 10s. Prompt de IMAGEN,
     literal del curso. Se pega en Flow con DOS imágenes adjuntas: el personaje
     de referencia y la prenda. La cara va SIEMPRE tapada por el móvil: en este
     formato la identidad es el cuerpo, el pelo y las manos, no la cara. -->

{
"reference_images": {
"character_reference": {
"source": "Use the provided character reference image exclusively as the character reference.",
"instructions": [
"Replicate the referenced person with maximum visual accuracy.",
"Preserve the same body shape, proportions, skin tone, hairstyle, hair color and apparent age.",
"The character must remain recognizably consistent in every generation.",
"Do not replace, reinterpret or randomly modify the referenced character.",
"The character's face must never be visible because it must be completely covered by the smartphone."
]
},
"clothing_reference": {
"source": "Use the provided clothing reference image exclusively as the outfit reference.",
"instructions": [
"Replicate the referenced clothing with maximum visual accuracy.",
"Preserve its exact design, cut, fit, length, silhouette, colors, pattern, fabric appearance, seams, decorations, rhinestones, prints, fastenings and proportions.",
"The clothing must fit the referenced character naturally.",
"Do not redesign, recolor, simplify, lengthen, shorten, replace or invent details.",
"Do not add garments that cover or alter important parts of the referenced clothing."
]
}
},
"subject": {
"description": "The person from the provided character reference image taking a casual full-body mirror selfie while wearing the exact clothing from the provided clothing reference image.",
"identity": "exactly the referenced character",
"appearance": "preserve the referenced character's body, skin tone, hairstyle, hair color and proportions",
"face_visibility": "the entire face must be completely hidden behind the smartphone",
"instructions": [
"The smartphone must cover the forehead, eyebrows, eyes, nose, cheeks, mouth and chin.",
"No facial feature may be visible around, above, below or beside the smartphone.",
"Do not generate the face in another part of the mirror reflection."
]
},
"pose": {
"position": "standing naturally in front of a full-length mirror",
"body_pose": "casual fashion pose with the body facing the mirror and one leg slightly forward or gently crossed in front of the other",
"phone_action": "one hand holds a smartphone vertically and directly in front of the face, completely covering the entire face",
"free_hand": "the other arm hangs naturally, rests lightly beside the body or holds a coordinated handbag",
"composition": "the full outfit remains clearly visible from the shoulders to the footwear while the smartphone completely conceals the face",
"variation": "slightly vary the stance, leg position, free-hand placement and phone angle in every generation",
"restrictions": [
"The smartphone must always remain centered directly over the entire face.",
"Do not place the smartphone beside, above or below the face.",
"Do not reveal the eyes, eyebrows, nose, cheeks, lips, mouth, jaw or chin.",
"Do not show the face through gaps around the smartphone.",
"Do not create an exaggerated runway pose.",
"Do not turn the character backward.",
"Do not hide the referenced clothing behind the phone, hair, arms or accessories.",
"Do not distort the body, hands, legs or reflection."
]
},
"clothing": {
"source": "Use the provided clothing reference image.",
"style": "the exact referenced outfit without random substitutions",
"instructions": [
"The referenced clothing must remain the main visual focus.",
"Preserve its exact fit and natural drape on the referenced character.",
"Keep every visible decorative detail accurately positioned.",
"Do not change the outfit according to the randomly generated scenario.",
"Do not generate a different dress, top, trousers, skirt or outerwear.",
"Do not copy the clothing's design or pattern onto accessories, walls, furniture or decorations."
]
},
"styling": {
"footwear": "generate exactly one matching pair of random fashionable modern autumn shoes or boots coordinated with the referenced clothing",
"handbag": "optionally include exactly one fashionable modern autumn handbag coordinated with the clothing and footwear",
"jewelry": "subtle contemporary jewelry may be added if it does not cover or alter the referenced clothing",
"instructions": [
"The footwear, handbag and jewelry may change in every generation.",
"Prioritize modern autumn styles such as tall boots, ankle boots, suede finishes, structured handbags and warm metallic jewelry.",
"Keep every accessory secondary to the referenced clothing.",
"Use autumnal neutral colors that complement the outfit.",
"Do not add readable brands, text or external logos.",
"Do not reproduce the clothing's exact decorative pattern on the accessories.",
"Do not generate mismatched shoes or additional footwear."
]
},
"hands_and_nails": {
"hands": "realistic feminine hands with anatomically correct fingers",
"fingernails": "elegant modern autumn manicure coordinated with the referenced clothing",
"rings": "optional delicate and fashionable finger rings",
"instructions": [
"The manicure and rings may vary in every generation.",
"Use sophisticated autumn shades such as burgundy, chocolate brown, caramel, taupe, dark cherry, nude or muted metallic tones.",
"Optional subtle rhinestones, glitter or metallic nail details are allowed.",
"Keep the smartphone grip natural and anatomically realistic.",
"Do not generate extra, missing, fused or deformed fingers.",
"Do not generate duplicated or floating rings, crystals or nail decorations."
]
},
"scenario": {
"setting": "a completely random, modern, sophisticated indoor autumn location suitable for a full-body mirror selfie",
"random_examples": [
"a luxurious modern bedroom decorated subtly for autumn",
"a contemporary apartment with warm wood finishes and seasonal details",
"a high-end modern dressing room with warm autumn decoration",
"a minimalist bedroom in caramel, cream and beige tones",
"a stylish modern loft with large windows and autumn foliage outside",
"an elegant contemporary hotel room with seasonal details",
"a modern walk-in wardrobe with warm ambient lighting",
"a fashionable apartment hallway with an oversized mirror",
"a sophisticated penthouse bedroom with an autumn city view",
"a modern boutique fitting room with warm seasonal styling"
],
"autumn_elements": [
"soft knitted blankets",
"warm textured rugs",
"modern wooden furniture",
"ceramic vases with dried autumn branches",
"subtle burgundy, brown and burnt-orange leaves",
"amber glass candles",
"minimal decorative pumpkins in elegant neutral colors",
"boucle or velvet furniture",
"warm beige, camel, terracotta, brown and burgundy accents",
"large windows showing softly blurred autumn foliage"
],
"instructions": [
"Generate a noticeably different modern autumn scenario in every generation.",
"Every environment must immediately communicate a cozy, fashionable and contemporary autumn atmosphere.",
"Randomize the room layout, furniture, mirror design, flooring, walls, decorative objects and autumn color palette.",
"Use modern furniture, clean architectural lines and tasteful seasonal decoration.",
"Keep the autumn elements elegant, realistic and naturally distributed.",
"Create a warm, cozy and aspirational atmosphere without making the room look old-fashioned or rustic.",
"The environment must look current, stylish, inhabited and suitable for modern social-media fashion content.",
"Include only a controlled number of tasteful autumn decorations and avoid visual clutter.",
"Do not reuse one fixed bedroom or an identical background composition.",
"Do not generate outdoor locations.",
"Do not create rustic farmhouses, traditional country interiors, vintage rooms or outdated furniture.",
"Do not create a photography studio, showroom or artificial commercial set.",
"Do not allow furniture or decorations to obstruct the character or referenced clothing."
]
},
"mirror_and_reflection": {
"mirror": "one large modern full-length mirror appropriate to the randomly generated autumn scenario",
"possible_styles": [
"minimal black-framed mirror",
"large arched mirror",
"frameless floor mirror",
"modern softly curved mirror",
"oversized warm-metal framed mirror"
],
"reflection": "physically coherent and correctly aligned with the character, smartphone, clothing and environment",
"instructions": [
"The reflected character must wear the exact referenced clothing.",
"The smartphone must completely cover the face in the reflection.",
"Do not reveal the face through another reflective surface.",
"Do not generate a second person outside the mirror.",
"Do not duplicate body parts, accessories, furniture or autumn decorations.",
"Do not add impossible reflections or inconsistent room geometry.",
"Keep the mirror clean enough for the complete outfit to remain visible."
]
},
"smartphone": {
"description": "one realistic modern smartphone held vertically and centered directly in front of the face",
"size_and_position": "large and close enough to completely cover the entire face from the forehead to the chin",
"case": "random fashionable phone case coordinated subtly with the autumn outfit and environment",
"instructions": [
"The smartphone case may vary in every generation.",
"The phone must completely conceal every facial feature.",
"Only the hair around the smartphone may remain visible.",
"Do not make the smartphone transparent.",
"Do not show the face on the smartphone screen.",
"Do not add readable branding, text, stickers or social-media graphics.",
"Do not generate additional phones."
]
},
"photography": {
"style": "authentic modern fashion UGC mirror selfie with a cozy autumn social-media aesthetic",
"camera_view": "vertical smartphone photograph captured through the mirror",
"framing": "full-body composition showing the referenced character, the complete referenced clothing and coordinated autumn footwear",
"aspect_ratio": "9:16 vertical",
"focus": "sharpest focus on the referenced clothing and character",
"perspective": "natural smartphone perspective with realistic mirror geometry",
"color_palette": "warm autumn palette with beige, caramel, chocolate brown, terracotta, burgundy, amber and muted cream tones",
"texture": "subtle smartphone grain, gentle softness and naturally imperfect details",
"quality": "photorealistic, spontaneous, attractive and non-commercial",
"variation": "slightly randomize the framing, camera height and distance while preserving a clear full-body view and complete facial coverage"
},
"lighting": {
"type": "warm, soft and modern autumn indoor lighting",
"possible_styles": [
"warm golden-hour light entering through a window",
"soft overcast autumn daylight",
"cozy amber bedside-lamp lighting",
"warm indirect architectural lighting",
"a combination of natural window light and soft amber lamps"
],
"effect": "warm highlights, soft realistic shadows, muted seasonal colors and an unmistakably cozy autumn mood",
"instructions": [
"The lighting may vary naturally in every generation but must always feel autumnal.",
"Favor warm amber, golden and soft neutral illumination.",
"Keep skin tones realistic and preserve the exact colors of the referenced clothing.",
"Use natural shadows and authentic smartphone exposure.",
"Do not use cold summer light, harsh white lighting, neon colors or bright tropical illumination.",
"Do not overexpose or obscure the referenced clothing.",
"Avoid harsh studio lighting and artificial fashion-catalogue illumination."
]
},
"atmosphere": {
"season": "autumn",
"mood": "warm, cozy, modern, fashionable and sophisticated",
"instructions": [
"The entire photograph must have a clearly recognizable autumn atmosphere.",
"Use warm color grading without applying a heavy artificial filter.",
"Create the visual feeling of a cool autumn afternoon or a cozy autumn evening.",
"The seasonal atmosphere must come from the lighting, color palette, textures and tasteful decorations.",
"Avoid Halloween styling, excessive pumpkins or exaggerated orange filters.",
"Do not create a Christmas, summer, spring or tropical atmosphere."
]
},
"restrictions": [
"Use exactly the person from the provided character reference image.",
"Use exactly the clothing from the provided clothing reference image.",
"The smartphone must completely cover the entire face.",
"Do not show any facial feature anywhere in the image or reflection.",
"Generate a different modern autumn indoor scenario in every generation.",
"Preserve the referenced character's body, skin tone, hairstyle, hair color and proportions.",
"Preserve every visible characteristic of the referenced clothing.",
"Show exactly one person and one coherent mirror reflection.",
"Show the complete outfit clearly from the shoulders to the footwear.",
"Do not generate additional people, faces, bodies, arms, hands, legs or phones.",
"Do not generate rustic, old-fashioned, tropical, summery or non-autumn environments.",
"Do not add text, captions, slogans, arrows, emojis, stickers or watermarks.",
"Do not reproduce any text visible in the example image.",
"Do not add TikTok interfaces, search bars, play buttons, usernames, shopping elements or social-media graphics.",
"Do not add phone status bars, borders, dates or fake camera overlays.",
"Do not create a studio photograph, catalogue image or polished commercial campaign.",
"Do not alter the referenced character or referenced clothing to match the random scenario."
],
"randomization": "The modern indoor autumn scenario, room layout, furniture, mirror design, seasonal decorations, lighting, footwear, handbag, jewelry, manicure, smartphone case and subtle pose must change in every generation. Every result must maintain a warm, modern and unmistakably autumnal atmosphere. The person from the character reference image and the clothing from the clothing reference image must remain exact, consistent and unchanged. The smartphone must always completely cover the character's entire face."
}
