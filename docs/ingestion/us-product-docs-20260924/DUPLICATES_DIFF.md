# US product docs: training guide vs PM product sheet comparison

Source: `pdftotext -layout <file>.pdf -` output of each source PDF. Line numbers `[Gnn]` = training-guide txt line, `[Snn]` = PM-sheet txt line.
Where the layout extraction was ambiguous, `pdftotext -raw` of the original PDF was checked (noted "raw").

## 0. General observations (apply to every pair)

| Topic | Finding |
|---|---|
| Document dates | All 9 training guides are browser-printed PDFs (Skia/Chrome, CreationDate **2026-09-22**), labelled "AI-ASSISTED CONTENT - INTERNAL GUIDANCE ONLY", "For Country Leadership", "based on the U.S. regulatory framework". Each says it is built from "the PM Page and FAQ" (some also an internal Product & Compliance Guide / Dossier Binder). They are newer files, but they are a derived, non-authoritative source. |
| PM sheet dates (filename code / PDF CreationDate) | Absorbent-D 061925 / 2025-06-19; AloeTurm 061925 / 2025-06-19; Freedom v4 090925 / 2025-09-19; Propolis Creme v4 012326 / 2026-01-23; Marine Collagen v11 051526 / 2026-05-15; B12 Plus 071526 / 2026-07-15; ImmuBlend 071626 / 2026-07-16; Aloe First 072326 / 2026-07-23. B12, ImmuBlend, Absorbent-D, AloeTurm carry embedded XMP dates from 2023/2024 (older template re-saved). |
| Supplement Facts | The PM sheets for Absorbent-D, AloeTurm, B12 Plus, ImmuBlend and Marine Collagen have **no Supplement Facts panel in the text layer** (it is an image or absent). Per-serving amounts in the guides can therefore only be marked ONLY-IN-GUIDE, not verified. Freedom is the only sheet with a text Supplement Facts panel. |
| Market markers | No metric-only units, no "international" wording in any sheet; all sheets are "US-EN". Guides say "U.S. regulatory framework" but are addressed to country leadership for local adaptation. Sheets for Propolis Creme, Aloe First (and Gelly) carry bilingual French INCI ("gel d'aloès officinal stabilisé", "Aqua/Eau"), i.e. a shared US/Canada label deck, which is not a contradiction. |
| Claim wording | The guides systematically tighten claim wording (their "AVOID" columns) and in several cases **ban wording that the current US sheet itself uses** (heart/cardiovascular, "protect", "proven", "rich blend", absorption). These are listed as CONTRADICTION (claim) below. |

---

## 1. Forever Absorbent-D (#672)

Guide: `Forever_Absorbent-D_Training_Guide.txt`. Sheet: `PM-Nutritionals-ForeverAbsorbantD-US-EN-061925__2_.txt` (the filename misspells "Absorbant").

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Name / item # | Forever Absorbent-D, SKU #672 [G3, G8] | Forever Absorbent-D, #672 [S1, S3] | MATCH |
| Format / flavor | Prickly pear chewable tablet [G28-30] | Prickly pear chewable tablets [S7-8] | MATCH |
| Net contents | 60 chewable tablets per bottle [G41, G102] | none (no CONTENTS block) | ONLY-IN-GUIDE |
| Directions | One chewable tablet twice daily [G88-89, G156] | One chewable tablet twice daily [S18-19] | MATCH |
| Serving size | 1 tablet [G102] | (implied: two tablets = 200% DV) [S16-17] | MATCH (implicit) |
| Vitamin D | 20 mcg (100% DV) per tablet, as cholecalciferol; 200% DV for 2 tablets [G34-35, G69, G99] | 20 mcg per tablet [S11]; 2 tablets = 200% DV [S16-17] | MATCH (the cholecalciferol source is only in the guide) |
| Vitamin E | 12 mg (80% DV), D-alpha tocopheryl acetate [G36, G72, G100-101] | "enhanced with vitamin E", no amount [S8, S12] | ONLY-IN-GUIDE (amount) |
| Total carbohydrate | <1 g (<1% DV) per tablet [G98] | none | ONLY-IN-GUIDE |
| Other ingredients / order | Listed by function, not label order: prickly pear, sorbitol & fructose, then "citric acid, natural orange flavor, stearic acid, magnesium stearate, silicon dioxide" [G76-84] | Sorbitol, fructose, prickly pear juice powder, citric acid, natural orange flavor, stearic acid, magnesium stearate, silicon dioxide [S27-29] | MATCH (same set; the guide does not give label order) |
| Certifications | Halal, Kosher [G39-40, G99] | Halal, Kosher [S23] | MATCH |
| Gluten/soy/dairy-free | Yes [G39, G98] | none | ONLY-IN-GUIDE |
| Vegan/vegetarian | Not vegetarian or vegan: D3 is from sheep's wool (lanolin) [G102-106, G172] | none | ONLY-IN-GUIDE |
| Sugar-free | Not sugar-free (sorbitol, fructose) [G102, G166] | "no artificial sweeteners" [S29] | MATCH / guide adds detail |
| Target age | Adults 18+; for a child, ask the child's doctor [G106, G159] | none | ONLY-IN-GUIDE (warning) |
| Multivitamin caution | Check with HCP if already taking D/E [G162] | none | ONLY-IN-GUIDE |
| Packaging | Fully recyclable [G180] | none | ONLY-IN-GUIDE |
| Absorption claim | "Chewable tablets **may** offer increased absorption" (SAY) [G209-211] | "Chewable tablets **offer** increased vitamin D absorption" [S5-6] | CONTRADICTION (claim strength, minor) |
| FDA disclaimer | Required [G364-367] | Present [S34-35] | MATCH |

---

## 2. Aloe Propolis Creme (#051)

Guide: `Forever_Aloe_Propolis_Creme_Training_Guide.txt`. Sheet: `PM-Bee-AloePropolisCreme-US-EN-v4-012326.txt`.

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Name / item # | Product #051, "Personal Care" [G12] | #051, category **BEE** [S1, S3] | MATCH # / category label differs (cosmetic) |
| Size | 4 oz. (113 g) tube [G35, G49, G134] | 4 OZ. (113 g) [S14] | MATCH |
| Directions | Apply liberally as needed, face and body; external use only; patch test; consult HCP in pregnancy [G100-103, G180] | Apply liberally as needed [S18]; patch test / pregnancy / external use in footer [S39-42] | MATCH ("face and body" only in the guide) |
| Certifications | IASC (aloe only), Halal, Kosher [G50-52, G108-110] | IASC, Halal, Kosher [S22] | MATCH |
| Aloe concentration | ">70% of the formula" (repeated) [G33-34, G40, G80, G119, G132] | none | ONLY-IN-GUIDE, and the guide contradicts itself at [G418-419]: "formulation percentages ... are internal-only and are not reflected in this guide" |
| **Ingredient list** | Aloe Barbadensis Leaf Juice, Glyceryl Stearate, Propylene Glycol, Cetyl Alcohol, PEG-100 Stearate, Lanolin, **Ethylhexyl Stearate, Ethylhexyl Palmitate, Sorbitol**, Allantoin, Propolis Extract, Lanolin Alcohol, Dimethicone, Tocopherol, Beta-Carotene, Corn Oil, Chamomile, **Diethylhexyl Adipate, 1,2-Hexanediol, Hydroxyacetophenone, Caprylyl Glycol, Ethylhexylglycerin, Hexylene Glycol, Water, Aminomethyl Propanol**, Disodium EDTA, Ascorbic Acid, **Chlorphenesin, Phenoxyethanol**, Fragrance [G151-155] | Aloe Barbadensis Leaf Juice, Glyceryl Stearate, Propylene Glycol, Cetyl Alcohol, PEG-100 Stearate, Lanolin, **Sorbitol, Ethylhexyl Palmitate, Ethylhexyl Stearate, Diethylhexyl Adipate**, Allantoin, Propolis Extract, Lanolin Alcohol, Dimethicone, Tocopherol, Beta Carotene, Corn Oil, Chamomile, **Triethanolamine**, Ascorbic Acid, Disodium EDTA, **Diazolidinyl Urea, Methylparaben, Propylparaben**, Fragrance [S26-35] | **CONTRADICTION** (two different formulations: different preservative system, different order) |
| Parabens | "Formulated without parabens"; "paraben-free, based on the current formula" [G108, G161-162, G363, G402] | Contains Methylparaben and Propylparaben [S34] | **CONTRADICTION** |
| Water | Present [G154] | Absent | CONTRADICTION (part of the formula change) |
| Shelf life / storage | 4 years from manufacture; keep tightly closed, cool and dry [G112, G146] | none | ONLY-IN-GUIDE |
| Manufacturer | Aloe Vera of America, Inc. [G36, G75, G137] | none | ONLY-IN-GUIDE |
| Dermatest approved | Yes [G142-143] | none | ONLY-IN-GUIDE |
| Vegan | No (lanolin) [G190-191] | none | ONLY-IN-GUIDE |
| Allergens | No nut, soy or gluten allergens [G193-194]; propolis is a known potential skin allergen, patch-test if bee-allergic [G208-210] | No bee-allergy statement (only a generic patch test [S40]) | ONLY-IN-GUIDE (warning) |
| Cruelty-free | Yes [G213] | none | ONLY-IN-GUIDE |
| Claim: "rich blend of aloe vera and bee propolis" | AVOID: propolis is at "trace level" [G225-229] | Fast fact [S5] | CONTRADICTION (claim) |
| Claim: propolis creates a skin barrier / rejuvenates | AVOID; credit aloe instead [G262-266, G394-395] | "creates a natural barrier", "rejuvenate skin's appearance" [S21-23, S26] | CONTRADICTION (claim) |
| Claim: chamomile "enhances the soothing power" | AVOID [G236-239] | Used [S27-28] | CONTRADICTION (claim) |

---

## 3. Forever AloeTurm (#676)

Guide: `Forever_AloeTurm_Training_Guide.txt`. Sheet: `PM-Nutritionals-ForeverAloeTurm-US-EN-061925__1_.txt`.

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Name / item # | Forever AloeTurm, #676 | Forever AloeTurm, #676 [S1, S3] | MATCH |
| Format / flavor | Soft hydrogel lozenge, natural mint [G28-29] | Hydrogel lozenge, natural mint [S5, S16] | MATCH |
| Actives | Turmeric (India) + zinc, no amounts [G72-75] | Turmeric (India), "fortified with zinc", no amounts [S13-14] | MATCH (neither gives amounts) |
| Net contents | 10 lozenges per carton [G48] | none | ONLY-IN-GUIDE (see note: 10 per carton at up to 4/day is only 2.5 days) |
| Directions | Dissolve slowly before swallowing; up to 4 lozenges/day [G89-91, G154] | Same [S20-22] | MATCH |
| Other ingredients + order | Glycerin, gelatin, water, soy lecithin, menthol, polysorbate 80, sucralose, eucalyptus oil, stevia, spearmint oil, star anise oil. Contains soy. [G77-82] | Identical order [S30-34] | MATCH |
| Allergen | Contains soy [G82, G95, G165] | Contains Soy [S34] | MATCH |
| Certifications | Halal (JUHF, India); NOT Kosher [G97-99, G171, G175-178] | Halal [S26] | MATCH (the certifying body and "not Kosher" are only in the guide) |
| Gelatin source | "bovine gelatin from a **non-cattle** source" [G99, G135, G168] | "gelatin" [S30] | ONLY-IN-GUIDE, and internally contradictory (bovine = cattle) |
| Sugar/gluten/dairy-free | Yes [G95, G165] | none | ONLY-IN-GUIDE |
| Target age | Adults 18+ [G101, G160] | none | ONLY-IN-GUIDE (warning) |
| Storage | Room temperature; can melt in sun/heat; refrigerate 1 hour to re-solidify [G157-158] | none | ONLY-IN-GUIDE |
| Manufacturing | Made in India by the patent-holding partner under AVA guidelines; third-party tested [G137-140] | none | ONLY-IN-GUIDE |
| Supplement/medication caution | Consult HCP if on other supplements or meds [G148-149] | none | ONLY-IN-GUIDE (warning) |
| Absorption claim | Do not imply AloeTurm "solves a general absorption problem"; no absorption promises [G242-244, G340-341] | "solves this issue ... absorbed directly by the body"; "Turmeric is absorbed directly by the body" [S9-11, S18-21] | CONTRADICTION (claim) |

---

## 4. Forever B12 Plus (#188)

Guide: `Forever_B12_Plus_Training_Guide.txt`. Sheet: `PM-Nutritionals-B12Plus-US-EN-071526__1_.txt`.

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Name / item # | Forever B12 Plus, #188 [G3, G10] | Forever B12 Plus, #188 [S1, S3] (body copy also says "Forever B12" [S47]) | MATCH |
| Contents | 60 tablets, 2-month supply [G47-48, G133] | 60 tablets [S13] | MATCH |
| Directions | One tablet daily, preferably after meals [G94-95, G167] | Same [S17-18] | MATCH |
| Vitamin B12 | 500 mcg cyanocobalamin, 20,833% DV [G30, G37-38, G138] | named only, no amount [S32] | ONLY-IN-GUIDE (amount) |
| Folic acid | 400 mcg (667 mcg DFE), 167% DV [G30-31, G41-42, G138-139] | named only [S32-33] | ONLY-IN-GUIDE (amount) |
| Other ingredients + order | Dextrose, dicalcium phosphate, HPMC, MCC, stearic acid, silicon dioxide, magnesium stearate [G142-143] | Identical order [S26-28] | MATCH |
| Certifications | Halal, Kosher [G50-51, G106, G188] | Halal, Kosher [S22] | MATCH |
| Vegan/vegetarian, gluten/dairy/soy-free | Yes (not certified) [G54-56, G108, G181-185] | none | ONLY-IN-GUIDE |
| Cautions | Consult HCP if pregnant, nursing or managing a condition; keep out of reach of children [G95-97, G207-210, G217-218] | none | ONLY-IN-GUIDE (warning) |
| Shelf life / storage | 4 years from packaging; away from heat and moisture [G74, G217-218] | none | ONLY-IN-GUIDE |
| Origin / manufacturer | Made in USA, Aloe Vera of America [G73, G221-222] | none | ONLY-IN-GUIDE |
| Claim: homocysteine and heart | AVOID any "heart"/"heart function" near homocysteine [G232-235, G421] | "Homocysteine ... contributes to heart function" [S39-40] | CONTRADICTION (claim) |
| Claim: "protect" | AVOID "protects you" [G244-246] | Headline "Essential B vitamins to energize and help protect" [S26] | CONTRADICTION (claim) |
| Claim: energy | "Helps support normal energy metabolism"; AVOID "boosts/gives energy" [G238-240] | "Supports energy production", "energize", "healthy energy levels" [S8, S26, S37] | CONTRADICTION (claim, mild) |

---

## 5. Forever Freedom (#896)

Guide: `Forever_Freedom_Training_Guide.txt`. Sheet: `PM-Drinks-Forever_Freedom_2025-US-v4-090925__3_.txt`.

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Name / item # | #896, "Nutritionals / Drinks" [G11] | #896, DRINKS [S1, S3] | MATCH |
| Contents | none | 33.8 fl oz (1 qt 1.8 fl oz) / 1 L [S20] | ONLY-IN-SHEET |
| Serving / servings | 4 fl oz [G102] | 4 fl oz (120 mL); about 8 servings [S48-49] | MATCH (servings only in the sheet) |
| Directions | 4 oz twice daily; shake; refrigerate after opening [G102-103, G178] | Same [S24-25] | MATCH |
| Caution / storage | Pregnant, nursing, medical condition or medication: consult HCP; seal; children; cool, dry, away from light [G105-110] | Same [S26-32] | MATCH |
| Glucosamine sulfate | 1,450 mg [G44, G87] | 1450 mg [S64] | MATCH |
| Chondroitin sulfate | 1,350 mg [G45, G91] | 1350 mg [S65] | MATCH |
| MSM | 650 mg [G49, G96] | 650 mg [S66] | MATCH |
| Other nutrients (cal 30, carb 7 g, sugars 5 g added, vit E 1.5 mg, Ca 32 mg, Na 150 mg, K 331 mg, protein 1 g) | none | [S53-62] | ONLY-IN-SHEET |
| Other ingredients | none | Stabilized aloe inner leaf gel, fructose, orange juice conc., lemon puree, ascorbic acid, citric acid, potassium sorbate, d-alpha tocopherol [S40-44] | ONLY-IN-SHEET |
| Certifications | Halal, IASC; NOT Kosher [G56-58, G113-115, G194-197] | Halal, IASC [S36] | MATCH ("not Kosher" is only in the guide) |
| Shellfish-free; glucosamine from non-GMO corn | Yes [G54, G165-169] | shellfish-free [S30] | MATCH / the corn source is only in the guide |
| Chondroitin source / vegan | Bovine; not vegan or vegetarian [G115-118, G188] | none | ONLY-IN-GUIDE |
| Gluten/dairy/soy-free | Yes [G57, G113, G191] | none | ONLY-IN-GUIDE |
| Packaging | 100% recyclable PET, 50% PCR; remove sleeve [G35, G148, G183] | Same [S64-66] | MATCH |
| Claim: "scientifically proven" | "scientifically **studied**" throughout [G7-8, G33] | "scientifically **proven**" [S5, S20, S25] | CONTRADICTION (claim) |
| Claim: aloe benefit | "normal digestive function and overall well being"; AVOID "boosts your immune system" [G41-42, G84, G221-223] | "Helps support gut and immune health and helps maintain natural energy" [S39-41] | CONTRADICTION (claim) |
| Use with Forever Move | Can be combined; consult HCP [G128, G171-173] | none | ONLY-IN-GUIDE |

---

## 6. Forever ImmuBlend (#355)

Guide: `Forever_ImmuBlend_Training_Guide_1.txt`. Sheet: `PM-Nutritionals-ForeverImmuBlend-US-EN-071626__3_.txt`.

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Name / item # | #355 [G456] | #355 [S3] | MATCH |
| Contents | 60 tablets, 30-day supply [G51-52, G140] | 60 tablets [S12] | MATCH |
| Directions | Two tablets daily [G101, G173] | Two tablets daily [S16-17] | MATCH |
| Caution | Consult HCP if pregnant, trying to conceive or nursing [G101-103, G198] | Same [S17-19] | MATCH |
| **Zinc** | Core active ("built on zinc, vitamin C, and vitamin D3") [G8, G32, G83] | **Not mentioned anywhere** (active list: FOS, lactoferrin, vit C & D, maitake, shiitake) [S18, S23-24, S33-39] | CONTRADICTION / ONLY-IN-GUIDE (unverifiable without the label panel) |
| Vitamin D form | D3 [G33, G86] | "Vitamin D" [S23, S37] | ONLY-IN-GUIDE (detail) |
| Mushrooms | Maitake mycelium powder + fruit-body extract; shiitake mycelium powder [G34-35, G94-96] | "maitake and shiitake mushrooms" [S24, S37] | ONLY-IN-GUIDE (detail) |
| Amounts | "See the Supplement Facts panel" [G146-147] | none in text | Neither |
| Other ingredients | none | MCC, HPMC, stearic acid, Mg stearate, croscarmellose Na, SiO2, Na CMC, dextrin, dextrose, soy lecithin, sodium citrate [S27-31] | ONLY-IN-SHEET |
| Allergens | Soy and milk [G185] | Contains Soy and Milk [S30-31] | MATCH |
| Certifications | Halal, Kosher Dairy [G53-54, G115, G189] | Halal, Kosher Dairy [S23] | MATCH |
| Gluten-free; vegetarian, not vegan | Yes [G115, G192-195] | none | ONLY-IN-GUIDE |
| Shelf life | 3 years from manufacture [G78, G218] | none | ONLY-IN-GUIDE |
| Probiotic? | Not a probiotic, no live bacteria [G153-155] | "promote healthy levels of probiotic bacteria" [S6-8, S19] | MATCH in substance; guide clarifies |
| Claim: gut % | Do not cite a percentage, say "a large share" [G251-255] | "approximately 70% to 80% of your body's immune cells reside in the gut" [S14-16] | CONTRADICTION (claim) |
| Claim: cardiovascular | Never add a cardiovascular/heart claim to vit C/D3 [G222, G258-260, G439] | "Vitamins C and D support immune cell function and cardiovascular function" [S23-24, S37-39] | CONTRADICTION (claim) |
| Claim: "proven ingredients" | not used | "natural botanicals and proven ingredients" [S11-12] | ONLY-IN-SHEET (claim risk) |

---

## 7. Forever Marine Collagen (#713)

Guide: `Forever-Marine-Collagen-Training-Guide.txt`. Sheet: `PM-Nutritionals-ForeverMarineCollagen-US-EN-v11-051526__4_.txt`.

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Name / item # | #713, "New Formula" [G11] | #713 [S4]; "Now featuring an updated formula" [S27] | MATCH |
| Contents | 30 x 0.43 fl oz (13 mL) sachets [G50-51] | Same [S20] | MATCH |
| Directions | One sachet daily, drink straight from the sachet [G94, G100, G200] | One sachet daily [S24] | MATCH |
| Cautions | Pregnant/nursing/condition/meds: consult HCP; damaged sachet; keep from children [G94-98] | Same [S24-29] | MATCH |
| Target age | **Adults only** [G94, G102, G158, G277-278, G408-409] | none | ONLY-IN-GUIDE (warning) |
| Fish collagen peptides | 3,000 mg [G38, G77] | 3,000 mg [S5, S23] | MATCH |
| Collagen tripeptides | 300 mg [G41, G83] | 300 mg [S8, S25] | MATCH |
| Zinc, biotin | Named, no amount [G44, G87-90] | Named, no amount [S29-30, S38-43] | MATCH |
| Sodium hyaluronate | "adds ... sodium hyaluronate" [G33, G149] | in ingredient list [S37] | MATCH |
| Other ingredients | Summarised: pomegranate extract, goji conc., red grape juice conc. [G172-173] | Full list: water, red grape juice conc., citric acid, **artificial grape flavor, artificial yogurt flavor**, xanthan gum, steviol glycosides, pomegranate, L-isoleucine, goji, sodium hyaluronate [S33-37] | ONLY-IN-SHEET (full list; the artificial flavors are not mentioned in the guide) |
| Allergen: fish species | Cod, haddock, pollock, sutchi catfish; no shellfish/crustacean/shark [G164, G170] | Contains: Fish (cod, haddock, pollock, sutchi catfish) [S38] | MATCH |
| Sourcing | Wild-caught, MSC certified, N. Atlantic/Pacific, made in Norway; tripeptides from farmed catfish [G57-58, G164-167] | "responsibly sourced, wild-caught fish" [S24] | ONLY-IN-GUIDE (the farm-raised tripeptide source nuances "wild-caught") |
| Certifications | MSC; Not IASC [G107-109, G219-221] | none (no CERTIFICATIONS block) | ONLY-IN-GUIDE |
| Diet | Free from GMO, **no added sugars**, gluten, dairy, soy [G107, G217-218] | red grape juice **concentrate** listed 2nd [S33] | ONLY-IN-GUIDE; possible conflict: fruit juice concentrate normally counts as added sugar on a US label |
| Calories / protein | 15 kcal, 4 g protein per sachet [G230] | none | ONLY-IN-GUIDE; plausibility: 3.3 g collagen would round to 3 g protein, and 4 g protein alone is 16 kcal |
| Infinite comparison | Infinite 790 mg / 2 tablets; no daily max [G121, G208-210] | none | ONLY-IN-GUIDE |

---

## 8. Aloe First (#040)

Guide: `Forever_Aloe_First_Training_Guide.txt`. Sheet: `PM-PersonalCare-AloeFirstSpray-US-EN-072326.txt`.

| Fact | Training guide [line] | Product sheet [line] | Status |
|---|---|---|---|
| Item # | **SKU 040R1** [G8]; "#040" in the source line [G352] | #040 [S3] | CONTRADICTION (minor: the R1 suffix suggests a reformulation or revision code) |
| Size | 16 fl oz (473 mL) [G30, G44, G125] | 16 FL. OZ. (1 pt.) (473 mL) [S16] | MATCH |
| Directions | Apply (FAQ: "spray") liberally as needed to soothe and moisturize; external use only [G88-89, G149] | Apply liberally ... external use only [S20-21] | MATCH |
| Patch test / pregnancy | In directions [G89-91] | In footer disclaimer [S53-56] | MATCH |
| Avoid contact with eyes | Yes [G152-153] | none | ONLY-IN-GUIDE (warning) |
| Certifications | IASC, Halal, Kosher, Cruelty Free [G47-48, G98, G132] | Same [S25] | MATCH |
| 11 botanicals | Chamomile, eucalyptus, sage, sandalwood, dandelion, yarrow, ginger, thyme, passion flower, borage, calendula [G81-83, G137-138] | Same 11 (Achillea = yarrow, etc.) [S32-40, S45-46] | MATCH |
| Propolis | "included as part of our botanical complex" [G78-79] | Separate key ingredient: "Helps soothe the skin and provides skin-conditioning benefits" [S12-15] | CONTRADICTION (framing, minor; the 11-count excludes propolis in both) |
| Full ingredient list | Partial (aloe, allantoin, glycerin, tocopherol, propolis, botanicals); "full list on label" [G136-139] | Full list incl. water, 1,2-hexanediol, hydroxyacetophenone, ascorbic acid, disodium EDTA, polysorbate 20 [S29-41] | ONLY-IN-SHEET |
| Bee-product allergen | none | none (contains propolis extract [S34]) | Omission in BOTH |
| Shelf life / storage | 4 years; cool, dry, sealed [G100, G158, G161] | none | ONLY-IN-GUIDE |
| Origin | Made in USA by Aloe Vera of America, globally sourced ingredients [G30-31, G67-68, G128-129] | none | ONLY-IN-GUIDE |
| pH-balanced, no-rub mist | Yes [G5, G28-29] | pH-balanced spray [S49] | MATCH |

---

## 9. Contradictions to decide

The suggested source is a suggestion, not a decision. "Label" means the physical US product label / current Supplement Facts, which neither document reproduces for most products.

| # | Product | Contradiction | Suggested authoritative source | Reason |
|---|---|---|---|---|
| C1 | Aloe Propolis Creme | **Ingredient list and preservative system differ.** The sheet has Triethanolamine, Diazolidinyl Urea, Methylparaben and Propylparaben. The guide has water, 1,2-Hexanediol, Hydroxyacetophenone, Caprylyl Glycol, Ethylhexylglycerin, Hexylene Glycol, Aminomethyl Propanol, Chlorphenesin and Phenoxyethanol. The order of sorbitol and the ethylhexyl esters also differs. | **Guide (newer formula), but verify against the current US label** | The guide says "based on the current formula" and was generated 2026-09. The 2026 Gelly (071426) and Aloe First (072326) sheets use the same new preservative system (1,2-hexanediol/hydroxyacetophenone/chlorphenesin/aminomethyl propanol). The Propolis sheet (v4, Jan 2026) looks like the pre-reformulation deck. |
| C2 | Aloe Propolis Creme | **Paraben-free** (guide) vs **contains methyl- and propylparaben** (sheet). | Same as C1 | This follows from C1. It is safety-relevant for customers who avoid parabens, so the chatbot must not say "paraben-free" until this is confirmed. |
| C3 | Aloe Propolis Creme | Guide states ">70% aloe", then says formulation percentages are internal-only and not in the guide [G418-419]. | Sheet (states no %) | The guide contradicts itself. Suppress the percentage unless Home Office confirms it is public. |
| C4 | Aloe Propolis Creme | Claim wording: the sheet's "rich blend of aloe vera and bee propolis", "natural barrier", "rejuvenate" and "enhances the soothing power ... chamomile" are all on the guide's AVOID list. | Sheet for "what the US page says"; guide for "what to say" | The sheet is the published US copy. The guide is a later compliance-tightened reading. Pick one policy for the chatbot. |
| C5 | AloeTurm | Gelatin "bovine ... from a **non-cattle** source" (guide, 3 times) is self-contradictory. The sheet just says "gelatin". | **Neither; ask Home Office** | Bovine means cattle. Probably a garble of "non-BSE" or "non-porcine". This matters for halal, vegetarian and religious questions. |
| C6 | AloeTurm | Absorption: the sheet says it "solves this issue" and turmeric is "absorbed directly by the body". The guide forbids implying it solves absorption. | Sheet for US copy; guide for safe wording | This is a claim-strength conflict, not a factual one. |
| C7 | AloeTurm | Pack size: the guide says "10 lozenges per carton" at up to 4/day (2.5 days). The sheet gives no count. | **Label** | The number looks implausible or refers to an inner pack. Do not state it until verified. |
| C8 | B12 Plus | Sheet: "Homocysteine ... contributes to heart function" and "help protect". Guide: never pair homocysteine with heart; no "protect". | Sheet for US copy; guide for safe wording | The sheet (Jul 2026) is the newest US page yet still carries wording the guide calls an implied cardiovascular claim. This needs a policy decision. |
| C9 | B12 Plus | Energy wording: the sheet's "supports energy production" and "energize" vs the guide's "normal energy metabolism" (AVOID "boosts energy"). | Guide wording | Mild. The guide wording is a subset of the sheet's meaning. |
| C10 | Freedom | "Scientifically **proven**" (sheet) vs "scientifically **studied**" (guide). | Guide wording | "Proven" is a stronger, substantiation-heavy claim. The guide deliberately softens it. The sheet (Sep 2025) is the oldest sheet. |
| C11 | Freedom | Aloe benefit: the sheet's "supports gut **and immune** health and ... natural energy" vs the guide's "normal digestive function and overall well being" (AVOID "boosts your immune system"). | Guide wording | The guide is later and more conservative. The sheet's immune/energy claim for aloe does not appear in the guide at all. |
| C12 | ImmuBlend | **Zinc**: the guide makes zinc a core active. The sheet text never mentions zinc. | **Label (Supplement Facts)** | The sheet's Supplement Facts is not in the text layer, so neither document proves the zinc content. The guide cites an internal compliance guide. |
| C13 | ImmuBlend | "70% to 80% of immune cells reside in the gut" (sheet) vs "don't cite a specific percentage" (guide). | Guide wording | The guide says the figure is not traceable to a measuring study. |
| C14 | ImmuBlend | "Vitamins C and D support ... **cardiovascular function**" (sheet) vs "never add a cardiovascular claim" (guide). | Guide wording (policy decision) | Same pattern as C8. The sheet (Jul 2026) is the newest US page. |
| C15 | Absorbent-D | "Chewable tablets **offer** increased absorption" (sheet) vs "**may** offer" (guide SAY column). | Sheet (fact); guide hedging optional | Minor claim-strength difference. |
| C16 | Aloe First | SKU "040R1" (guide) vs "#040" (sheet). | Sheet for the public item number | R1 is likely an internal revision suffix. The guide's own source line cites #040. |
| C17 | Aloe First | Propolis is a separate soothing ingredient (sheet) vs "part of our botanical complex" (guide). | Sheet | This is the US page wording. Both agree the 11-botanical count excludes propolis. |
| C18 | Marine Collagen | "No added sugars" (guide) vs red grape juice concentrate as the 2nd ingredient (sheet). | **Label** | Under US labeling, juice concentrate beyond single strength normally counts as added sugar. Verify before repeating "no added sugars". |
| C19 | Marine Collagen | 15 kcal / 4 g protein (guide) vs 3,300 mg collagen actives (both). | **Label** | 3.3 g collagen would round to 3 g protein, and 4 g protein alone is 16 kcal before any grape sugars. The numbers are borderline, so check the panel. |

**Safety-relevant omissions** (not contradictions, but the sheet lacks a warning the guide has; the chatbot should not rely on the sheet alone):
- Absorbent-D: adults 18+ only; not vegan/vegetarian (lanolin-derived D3). The sheet also has no net-contents line.
- AloeTurm: adults 18+; not Kosher; bovine gelatin (see C5); melts in heat.
- B12 Plus: pregnancy/nursing caution and keep out of reach of children.
- Marine Collagen: adults only.
- Aloe Propolis Creme: bee-product (propolis) allergy caution; contains lanolin.
- Aloe First: avoid eyes. Neither document has a bee-product (propolis) allergy caution.

**Which is newer?** Every guide PDF is newer (2026-09-22) than its sheet. But the guides are AI-assisted derivatives that cite "the PM Page" as their source, so on label facts the sheet (or the physical label) should win. The exception is Propolis Creme, where the guide appears to reflect a later formulation. On claim wording, the guides consistently reflect a later compliance review.

---

## 10. Sheet-only products and the iVision guide: internal inconsistencies

| Product (doc) | Issue [line, raw extraction] |
|---|---|
| **Forever Pro-B Ultra #710** (sheet 091026) | "Non-GMO Project certified" strains [raw 39] are not in the CERTIFICATIONS line (Halal, Kosher only) [raw 18]. Strain names use pre-2020 taxonomy ("Lactobacillus rhamnosus GG", "L. plantarum") [raw 37-38]. The sheet says "free from ... major allergens" but the text layer has no strain/amount panel to confirm 10 strains / 10 billion CFU. 30 capsules at 1/day is consistent. |
| **Forever Aloe Vera Gel #815** (PET, sheet v2 031226) | No serving size or daily amount in DIRECTIONS, only "Shake well. Refrigerate after opening" [raw 10-11]. "No added preservatives" [raw 3, 33-34] sits beside ascorbic acid and citric acid in the ingredient declaration [raw 15-16]; these act as stabilizers, which is a wording risk. The fast fact "Promotes immune health" [raw 5] is not supported elsewhere in the body copy. |
| **Forever Fiber Fusion #702** (sheet 051126) | The fiber blend (non-GMO corn fiber, fruit fiber) and zinc gluconate are claimed [raw 33-35, 52] but absent from OTHER INGREDIENTS [raw 20-23]. Presumably they sit in the Supplement Facts image, but the text is not self-contained. Contains aloe vera juice powder but lists no IASC certification. No caution, children or pregnancy statement at all. 29 g = 1.02 oz is consistent. |
| **Forever Kids #354** (sheet 080826) | Dosing gap: "children **over four** and adults: 4 tablets", "children **one to three**: 2 tablets" [raw 12-16]. Age 4 exactly is not covered, and under 1 is only implied by "formulated for children one year and older" [raw 45]. "No ... artificial flavors, colors" [raw 6] while the ingredients include **sucralose** [raw 24] (an artificial sweetener, not strictly a contradiction, but misleading for a kids product). 120 tablets at 4/day = 30 days, or 60 days for toddlers. "Raw broccoli ... and 18 other fruits and vegetables" cannot be verified (no ingredient in the list names them). |
| **Forever Bright Toothgel #028** (sheet 020326) | A cosmetic/oral-care product carries the **dietary-supplement FDA disclaimer** [raw 37-38] instead of the cosmetic disclaimer used on the other personal-care sheets. "Natural peppermint and spearmint" [raw 30] vs "Flavor (Aroma)" in the ingredients [raw 19]. "Combines aloe vera with other natural ingredients" vs SLS, sodium saccharin, sodium benzoate [raw 18-20]. "Safe and suitable for the entire family" [raw 35-36] with no age or supervision guidance for young children. Contains propolis with no bee-allergy caution. |
| **Aloe Vera Gelly #061** (sheet 071426) | Internally consistent (4 fl oz = 118 mL; IASC is appropriate for stabilized gel). Its preservative system (1,2-hexanediol, hydroxyacetophenone, chlorphenesin, aminomethyl propanol) is the evidence used for C1. |
| **Forever Aloe Lips #022** (sheet 070726) | "Lock in moisture with aloe vera and other **natural** ingredients" / "natural and naturally derived ingredients" [raw 23-24, 31-32] while the first two ingredients are **petrolatum and mineral oil** and it contains **propylparaben** [raw 13, 18]. The aloe is "Leaf Extract", low in the list, with no IASC (consistent with not certifying). Contains soybean oil and beeswax with no allergen statement [raw 14-16]. 0.15 oz = 4.25 g is consistent. |
| **Forever iVision #624** (guide only) | No ingredient amounts anywhere (no Supplement Facts). "Softgel coloring from natural black carrot juice **and zinc oxide**" [G161] but zinc oxide is not in the "Also contains" list, which lists "black carrot concentrate (natural coloring)" [G95-98]. The bilberry "eye circulation / reduce eye fatigue" claim appears only in the SAY table [G225-227], which says "Source uses..." although Sections 1-3 only say "traditional botanical ... eye wellness" [G39-41, G84-86]. **No minimum age** despite recommending it for "children, teens, and adults" [G362-364] and citing children aged 8-10 [G185-186]; there is also no pregnancy or medication caution. "Breakthrough" and "enhances glare recovery time" are stronger than its own "supports/helps" rule [G28, G49, G238-239]. Contains beeswax and fish (tilapia) gelatin; no bee allergen note. 60 softgels at 2/day = 30 days is consistent. |
