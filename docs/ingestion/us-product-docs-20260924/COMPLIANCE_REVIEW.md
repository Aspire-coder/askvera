# Forever Living US Documents: Claims Inventory (Flag for Review)

Prepared as input to a compliance review. **This does not decide legality or compliance.** Every item below is "flag for review" only.

- Source: 24 `pdftotext -layout` extractions (regenerate any file with `pdftotext -layout <file>.pdf -`) (9 training guides, 15 US product sheets). All 24 files were read in full.
- Line references (`Lnn`) are line numbers in the matching `.txt` file. Because the layout extraction merges columns, one line can mix text from two columns. Quotes are trimmed to the relevant column.
- **Severity key:** HIGH = disease, drug-like, cure/treat/prevent wording, or claims about children or pregnancy. MEDIUM = structure/function (S/F) claims with no adjacent disclaimer, clinical/study/"science" claims, comparative or bioavailability claims. LOW = general wellness or cosmetic/appearance claims.
- **Asterisk linkage:** no document links any claim to a disclaimer with an asterisk. The only asterisks, in the Forever Freedom product sheet, belong to the %DV footnote. So every item's "Asterisk?" value is **No**, and the column is left out below. Each supplement disclaimer sits once at the foot of its document, away from the "Fast Facts" claims. That is why S/F claims are rated MEDIUM.
- **Counter-examples:** training guides have "AVOID / DON'T SAY" columns full of disease words (arthritis, colds, osteoporosis, cancer, macular degeneration and more). These are negative examples, not claims. They are listed separately under each guide and left out of the claim counts, so keyword-based screening does not misread them.
- **Shared guide boilerplate:** all 9 training guides open (about L11-L23) with "AI-ASSISTED CONTENT - INTERNAL GUIDANCE ONLY - LOCAL REVIEW AND APPROVAL REQUIRED". It adds that including a claim "does not establish that it is substantiated, approved, or authorized". Flag for review: the guides are AI-assisted and say they are not approved consumer copy.

---

## 1. Summary table

| # | File | Doc type | # claims flagged | Highest severity (driver) | FDA disclaimer present? |
|---|------|----------|-----------------:|---------------------------|--------------------------|
| 1 | PM-Bee-AloePropolisCreme-US-EN-v4-012326.txt | Product sheet (cosmetic) | 10 | HIGH (propolis "natural barrier": skin-protectant/drug-like) | **Partial.** Cosmetic variant at L39-42 ("Forever makes no claim that its products cure or prevent any diseases..."). Not DSHEA wording. Footer only, no asterisks. |
| 2 | PM-Drinks-ForeverAloeVeraGelPET-US-EN-v2-031226.txt | Product sheet (drink/supplement) | 8 | MEDIUM (immune/digestion S/F; "scientific experts") | **Yes.** Full FDA text at L42-43, footer, no asterisks. No cautions of any kind. |
| 3 | PM-Drinks-Forever_Freedom_2025-US-v4-090925__3_.txt | Product sheet (supplement) | 13 | MEDIUM (reviewer may raise to HIGH): "scientifically proven"; joint "comfort" is pain-adjacent | **Yes.** L70-71, footer, beside Supplement Facts. Asterisks only for %DV. |
| 4 | PM-Nutritionals-B12Plus-US-EN-071526__1_.txt | Product sheet (supplement) | 10 | HIGH (homocysteine "contributes to heart function"; "help protect") | **Yes.** L50-51, footer, no asterisks. No cautions on the sheet. |
| 5 | PM-Nutritionals-Fiber_Fusion-US-EN-051126__2_.txt | Product sheet (supplement) | 10 | HIGH ("May help ease occasional bloating and irregularity"); satiety/weight-adjacent | **Yes.** L50-51, footer, no asterisks. No cautions. |
| 6 | PM-Nutritionals-ForeverAbsorbantD-US-EN-061925__2_.txt | Product sheet (supplement) | 10 | MEDIUM ("Studies have shown"; unqualified "increased absorption") | **Yes.** L34-35, footer, no asterisks. No age limit or cautions (the guide says adults 18+). |
| 7 | PM-Nutritionals-ForeverAloeTurm-US-EN-061925__1_.txt | Product sheet (supplement) | 12 | HIGH ("fortify your body's defenses"; "revolutionary... solves this issue") | **Yes.** L36-37, footer, no asterisks. No age limit or pregnancy caution (the guide says 18+). |
| 8 | PM-Nutritionals-ForeverImmuBlend-US-EN-071626__3_.txt | Product sheet (supplement) | 14 | HIGH (germs/viruses; C & D "cardiovascular function"; "70% to 80%" statistic) | **Yes.** L45-46, footer, no asterisks. Pregnancy caution at L17-19. |
| 9 | PM-Nutritionals-ForeverKids-US-EN-080826__1_.txt | Product sheet (children's supplement) | 13 | HIGH (whole document targets children; dosing for ages 1-3; iron and cognition) | **Yes.** L40-41, footer, no asterisks. No iron accidental-overdose warning in the sheet (check the physical label). |
| 10 | PM-Nutritionals-ForeverMarineCollagen-US-EN-v11-051526__4_.txt | Product sheet (supplement) | 14 | MEDIUM (wrinkles claim for an ingestible; "scientifically advanced"; bioavailability comparison) | **Yes.** L58-59, footer, no asterisks. Pregnancy caution at L24-29. No "adult use only" line (the guide says it is on the label). |
| 11 | PM-PersonalCare-AloeFirstSpray-US-EN-072326.txt | Product sheet (cosmetic) | 13 | LOW (soothe/moisturize; "moisture relief") | **Partial.** Cosmetic variant at L53-56, footer. |
| 12 | PM-PersonalCare-ForeverBrightToothgel-US-EN-020326__1_.txt | Product sheet (cosmetic oral care) | 11 | HIGH ("for the whole family" / "safe and suitable for the entire family" with no age directions); gum claims are gingivitis-adjacent | **Mismatch.** The **dietary-supplement** FDA text appears at L46-47 on a cosmetic toothgel. No Drug Facts. Fluoride-free. No child-use warnings. |
| 13 | PM-SkinCare-AloeVeraGelly-US-EN-071426__1_.txt | Product sheet (cosmetic) | 8 | MEDIUM (first-aid-style directions: "Thoroughly cleanse skin in area...") | **Partial.** Cosmetic variant at L46-49. |
| 14 | PM-SkinCare-ForeverAloeLips-US-EN-070726__2_.txt | Product sheet (cosmetic lip) | 9 | MEDIUM ("lasting moisture barrier" with petrolatum listed first, protectant-adjacent) | **Partial.** Cosmetic variant at L45-48. No SPF claim. |
| 15 | PM_Nutritionals_-_Forever_Pro-B_Ultra_-_US_-091026__1_.txt | Product sheet (supplement) | 14 | MEDIUM ("most clinically studied and tested probiotic strains") | **Yes.** L46-47, footer, no asterisks. No cautions. |
| 16 | Forever-Marine-Collagen-Training-Guide.txt | Training guide | 27 | MEDIUM ("Emerging research suggests"; wrinkles; "Dalton size... scientifically disproven") | **Yes.** Instruction to use it at L447-449, plus a footer at L460-462. Noted in the Section 4 table (L280-281). No asterisks. |
| 17 | Forever_Absorbent-D_Training_Guide.txt | Training guide | 23 | MEDIUM ("Studies have shown"; absorption claims; child referral) | **Partial.** Quoted inside the instruction at L364-367, with "pair every benefit mention" at L227-230 and L236. **No standalone footer disclaimer.** The closing note at L375-377 replaces it. |
| 18 | Forever_AloeTurm_Training_Guide.txt | Training guide | 21 | MEDIUM ("it's still effective"; "maximize the product's benefits") | **Yes.** L219-222 (table), L386-388 (instruction), footer L393-395. |
| 19 | Forever_Aloe_First_Training_Guide.txt | Training guide (cosmetic) | 17 | MEDIUM (use on children and sunburn questions handled without a firm answer) | **Partial.** Cosmetic variant at L211-216, L342-345, and footer L350-352. |
| 20 | Forever_Aloe_Propolis_Creme_Training_Guide.txt | Training guide (cosmetic) | 18 | HIGH (eczema/psoriasis/rosacea answer: "can be part of your regular moisturizing routine alongside their guidance") | **Partial.** Cosmetic variant at L248-253, L410-413, and footer L415-416. |
| 21 | Forever_B12_Plus_Training_Guide.txt | Training guide | 29 | HIGH (metformin and acid-reducer interaction content; pregnancy and folic acid) | **Yes.** L406-409 (table), L435-437 (instruction), footer L439-441. |
| 22 | Forever_Freedom_Training_Guide.txt | Training guide | 21 | MEDIUM ("scientifically studied"; seniors/aging; comfort during movement) | **Yes.** L237-239 (table), L404-406, footer L417-419. |
| 23 | Forever_ImmuBlend_Training_Guide_1.txt | Training guide | 31 | HIGH (cold/flu-season answers; "proactive... not for treating illness once it's already here"; zinc and common cold) | **Yes.** L267-272 ("verbatim"), L406 ("at the top"), L435-437, footer L454-456. |
| 24 | Forever_iVision_Training_Guide.txt | Training guide (no matching product sheet in the input set) | 39 | HIGH (children; blue-light retinal harm; "first line of defense"; "reduce eye fatigue"; "breakthrough") | **Yes.** L233-234 (table), L397-399, footer L408-410. **No pregnancy, medication, age or keep-out-of-reach cautions anywhere in the guide.** |

**Totals:** 395 flagged statements (product sheets 169, training guides 226), plus counter-examples listed separately.

---

## 2. Per-file findings

### Product sheets

#### 1. PM-Bee-AloePropolisCreme-US-EN-v4-012326.txt (cosmetic, #051)
1. L5: "Rich blend of aloe vera and bee propolis". Benefit/positioning. **MEDIUM.** The Propolis guide's AVOID column (L225-229) names this exact phrase; propolis is present at trace level.
2. L6-8: "Helps maintain beautiful skin tone and texture". Cosmetic. LOW.
3. L9: "Nourishing and moisturizing". Cosmetic. LOW.
4. L10: "Helps soothe skin". Cosmetic (soothe). LOW.
5. L19: "help your skin maintain beautiful tone and texture". Cosmetic. LOW.
6. L22-23: propolis "has properties that create a natural barrier on your skin, locking in the natural skin care benefits". Drug-like (skin-protectant style). **HIGH.** The guide (L262-263, L394-395) says never credit propolis with a barrier.
7. L25-26: aloe "nourishes and moisturizes the skin". Cosmetic. LOW.
8. L26-27: "bee propolis helps rejuvenate skin's appearance for a smoother, suppler look". Cosmetic/anti-aging. **MEDIUM.** The guide (L173-175, L367-369) says "rejuvenate" is not language it would use.
9. L27-28: "enhances the soothing power of aloe with the addition of chamomile". Benefit. **MEDIUM.** The guide AVOID column (L236-239) says chamomile is below an effective level.
10. L36-37: "Treat your skin to the soothing, nourishing power". Cosmetic ("treat" used loosely; will trip keyword filters). LOW.
- **Disclaimer:** cosmetic variant at L39-42, which also says to patch test, consult a professional during pregnancy, and use externally only. It is not the DSHEA FDA text.
- **Other flag:** the ingredient list (L30-34) includes **Methylparaben and Propylparaben**. The Propolis training guide calls the product paraben-free (L108, L161-162, L402), and its ingredient list (L151-155) differs. There is a document version conflict.

#### 2. PM-Drinks-ForeverAloeVeraGelPET-US-EN-v2-031226.txt (drink, #815)
1. L7: "Supports healthy digestion". S/F. MEDIUM.
2. L8: "Promotes immune health". S/F. MEDIUM.
3. L9: "Supports nutrient absorption". S/F. MEDIUM.
4. L10: "Helps maintain natural energy levels". S/F. MEDIUM.
5. L17-18: "helps support your overall well-being". General wellness. LOW.
6. L21-22: Aloe Barbadensis Miller is "the most nutritionally valuable variety". Comparative/superlative. MEDIUM.
7. L26-27 and L37-38: "supported by a team of scientific experts". Clinical/expert endorsement. MEDIUM.
8. L31-32: "preserve freshness and potency". Quality. LOW.
- **Disclaimer:** full FDA text at L42-43, footer only.
- **Warnings:** none (no pregnancy, medication or children caution). Flag the missing cautions for review.

#### 3. PM-Drinks-Forever_Freedom_2025-US-v4-090925__3_.txt (supplement drink, #896)
1. L5-6: "Formulated with scientifically proven ingredients that support joints". Clinical. MEDIUM. The Freedom guide says "scientifically studied" throughout, which is an escalation mismatch.
2. L9: "Helps maintain cartilage health". S/F. MEDIUM.
3. L10: "Supports joint function and mobility". S/F. MEDIUM.
4. L11-13: "Supports cartilage and joint lubrication function". S/F. MEDIUM.
5. L20-21: "Move more freely with scientifically proven joint support". Clinical. MEDIUM.
6. L23: "helps you move with comfort and confidence". S/F, pain-adjacent. MEDIUM.
7. L25-27: "three scientifically proven ingredients that promote joint function and mobility". Clinical. MEDIUM.
8. L34-36: "maintain your joint health... promoting comfort and mobility". S/F, pain-adjacent. MEDIUM.
9. L39-40: aloe "Helps support gut and immune health and helps maintain natural energy". S/F. MEDIUM.
10. L39-43: chondroitin "helps the body's natural ability to cushion joints". S/F. MEDIUM.
11. L46-48: MSM "Helps maintain healthy joints and cartilage while contributing to joint comfort during movement". S/F, pain-adjacent. MEDIUM (reviewer may treat it as an implied pain-relief claim, which would be HIGH).
12. L47-49: glucosamine "Helps support cartilage and joint health... compound found in joint fluids". S/F. MEDIUM.
13. L67-68: "same trusted benefits... supports active living and feeling your best". General wellness. LOW.
- **Disclaimer:** FDA text at L70-71. The asterisks at L53, L56 and L68 are tied to %DV, not to claims.
- **Warnings:** L26-32 covers pregnancy, nursing, medical conditions and medication, a broken seal, and keeping it out of reach of children.

#### 4. PM-Nutritionals-B12Plus-US-EN-071526__1_.txt (supplement, #188)
1. L5-6: "Helps maintain healthy homocysteine levels already within the normal range". S/F. MEDIUM.
2. L8: "Supports energy production". S/F. MEDIUM.
3. L9: "Helps support normal immune function". S/F. MEDIUM.
4. L26: "Essential B vitamins to energize and help protect". Drug-like/prevention-adjacent. **HIGH.** The B12 guide (L243-246) says an unqualified "protect" reads as disease prevention. It also lists "gives you more energy" under AVOID (L238-241).
5. L28-30: "many people aren't getting enough... especially true for vegans, vegetarians". Deficiency-adjacent. MEDIUM.
6. L32-35: "helps assist in the production of red blood cells, and helps promote normal immune function". S/F (anemia-adjacent). MEDIUM.
7. L37: "helps promote healthy energy levels". S/F. MEDIUM.
8. L39-40: "Homocysteine is a naturally occurring amino acid that contributes to heart function". Disease-adjacent (implied cardiovascular). **HIGH.** It directly conflicts with guide L232-236 and L421-422 ("never pair the homocysteine claim with heart").
9. L42-45: B12 "healthy energy levels... normal immune function"; folic acid "metabolic processes and normal immune function". S/F. MEDIUM.
10. L47: "Help your body feel its best". General wellness. LOW.
- **Disclaimer:** L50-51.
- **Warnings:** none on the sheet. The guide (L95-97) quotes a label caution about pregnancy, nursing and medical conditions, and keeping it out of reach of children. Flag the missing caution.

#### 5. PM-Nutritionals-Fiber_Fusion-US-EN-051126__2_.txt (supplement, #702)
1. L5: "8 grams of fiber per serving". Nutrient content. LOW.
2. L6-8: "Supports digestive health and a feeling of fullness". S/F plus **weight-adjacent** (satiety). MEDIUM.
3. L11: "Helps feed the gut". S/F. MEDIUM.
4. L12-14: "May help ease occasional bloating and irregularity". Drug-like verb ("ease") plus GI symptoms. **HIGH.** It carries the "occasional" qualifier.
5. L15-17: "sources of fiber that are easy to digest". LOW.
6. L24-25: "helps support healthy digestion and a feeling of fullness". S/F, weight-adjacent. MEDIUM.
7. L30-32: "may help ease occasional bloating and irregularity... helps nourish beneficial gut bacteria". Drug-like and S/F. **HIGH.**
8. L35: "Helps support healthy digestion and a feeling of fullness". S/F, weight-adjacent. MEDIUM.
9. L40: zinc "Helps support metabolism function". S/F (metabolism, weight-adjacent). MEDIUM.
10. L42-45: "help fill potential nutritional gaps... support your wellness routine". LOW.
- **Disclaimer:** L50-51.
- **Warnings:** none (no caution, children or choking statement for the jelly format). Flag for review.

#### 6. PM-Nutritionals-ForeverAbsorbantD-US-EN-061925__2_.txt (supplement, #672)
1. L5-6: "Chewable tablets offer increased vitamin D absorption". Bioavailability, unqualified. MEDIUM. The guide's SAY wording (L210) is "may offer".
2. L7-8: "chewable tablets with enhanced absorption". Bioavailability. MEDIUM.
3. L9: "May promote a healthy immune system". S/F. MEDIUM.
4. L10: "Helps maintain strong bones". S/F (osteoporosis-adjacent). MEDIUM.
5. L13-14: "help enhance your daily wellness routine". LOW.
6. L15-16: "Studies have shown it can be difficult to get enough vitamin D through diet and sunlight alone". Clinical (unnamed studies). MEDIUM.
7. L17-18: "200% of the U.S. recommended daily value... support this common nutritional gap". Deficiency-adjacent. MEDIUM.
8. L19-20: "vitamin D support immune health and help maintain strong bones". S/F. MEDIUM.
9. L20-21: "antioxidant vitamin E helps protect cells from oxidative stress". S/F. MEDIUM.
10. L30: "support your immune health and overall wellness". S/F. MEDIUM.
- **Disclaimer:** L34-35.
- **Warnings:** none, and no age statement, although the guide (L106, L159, L183) says "Recommended for adults 18+". Flag.

#### 7. PM-Nutritionals-ForeverAloeTurm-US-EN-061925__1_.txt (supplement lozenge, #676)
1. L5-6: "Hydrogel lozenge technology easily dissolves and digests". LOW.
2. L7-8: "Support your immune health with an innovative hydrogel lozenge". S/F. MEDIUM.
3. L9-11: "Turmeric is absorbed directly by the body due to the dissolving technology". Bioavailability. MEDIUM. The guide (L340-341) says not to promise absorption.
4. L10: "Maintaining a healthy immune system is crucial". LOW.
5. L11-12: "a revolutionary hydrogel lozenge for enhanced absorption to support immunity". Superlative plus bioavailability. MEDIUM.
6. L13-15: "designed to support immune health". S/F. MEDIUM.
7. L15: "Supports immune health". S/F. MEDIUM.
8. L16-17: turmeric "an ancient Ayurvedic herb... to aid in natural living". Traditional use. LOW.
9. L18-21: "biggest challenges with turmeric is its low absorption... Forever AloeTurm solves this issue". Bioavailability/efficacy. **MEDIUM.** It contradicts guide L242-244 ("without implying... AloeTurm solves a general absorption problem").
10. L22: "promote your immune health". S/F. MEDIUM.
11. L23: "provides a soothing feeling in the mouth". LOW. Note: a menthol/eucalyptus lozenge that "soothes" could be read as a sore-throat implication.
12. L24-25: "a convenient way to fortify your body's defenses". Disease-prevention-adjacent. **HIGH.**
- **Disclaimer:** L36-37.
- **Warnings:** soy allergen only. No 18+ age limit (guide L101, L160) and no pregnancy or medication caution. Flag.

#### 8. PM-Nutritionals-ForeverImmuBlend-US-EN-071626__3_.txt (supplement, #355)
1. L5: "Supports immune cell function". S/F. MEDIUM.
2. L6-8: "Promotes healthy levels of probiotic bacteria". S/F. MEDIUM.
3. L7: "Comprehensive nutritional support for immune function". S/F. MEDIUM.
4. L9: "Every day you are exposed to germs, bacteria and viruses". Disease-adjacent (infection framing). **HIGH.**
5. L11-12: "natural botanicals and proven ingredients". Clinical. MEDIUM.
6. L14-16: "Science supports that approximately 70% to 80% of your body's immune cells reside in the gut". Clinical statistic. **MEDIUM.** It conflicts with guide L252-254 and L448-449 ("don't cite a specific percentage"; "not traceable to a study").
7. L16-17: "safeguarding your digestive health... helping support your immune system". S/F. MEDIUM.
8. L18-19: FOS and lactoferrin "promote healthy levels of probiotic bacteria and support immune cell function". S/F. MEDIUM.
9. L21-22: "delivers immune support beyond the digestive system... whole-body approach". S/F. MEDIUM.
10. L23-24: "Vitamins C and D support immune cell function and cardiovascular function". Disease-adjacent (cardiovascular). **HIGH.** It conflicts with guide L258-259 ("current evidence at these doses does not show a cardiovascular benefit") and L439.
11. L24-25: mushrooms "provide antioxidant support and help support immune health". S/F. MEDIUM.
12. L33-35: FOS and lactoferrin panel: "Support immune cell function and promote healthy levels of probiotic bacteria". S/F. MEDIUM.
13. L37-39: Vitamins C and D panel: "Support immune cell function and cardiovascular function". **HIGH**, a repeat of item 10.
14. L41-43: "combines the best of science and nature... Be proactive in supporting daily immune wellness". Clinical and prevention-adjacent ("proactive"). MEDIUM.
- **Disclaimer:** L45-46.
- **Warnings:** L17-19 (pregnant, trying to conceive, nursing). Allergens: soy and milk (L30-31).

#### 9. PM-Nutritionals-ForeverKids-US-EN-080826__1_.txt (children's supplement, #354)
1. L5-6: "Supports healthy growth and development". Children, S/F. **HIGH.**
2. L7: "Delicious multivitamin support for growing kids". Children. **HIGH.**
3. L8-9: "Provides essential vitamins, minerals and nutrients for growing bodies". Children. **HIGH.**
4. L11-13: "support healthy growth and development with nutrients designed for growing bodies and minds". Children plus cognition. **HIGH.**
5. L15-16: "specifically formulated for the nutritional needs of children". Children. **HIGH.**
6. L16-17: "Vitamin C helps support normal immune function". S/F in a children's product. **HIGH.**
7. L17-18: "vitamin D3 supports normal growth and development". Children, S/F. **HIGH.**
8. L18-19: "Iron contributes to normal cognitive function and energy metabolism". Children plus cognition. **HIGH.**
9. L19-20: "vitamin B12 also contributes to energy metabolism". Children, S/F. **HIGH.**
10. L22-25: dosing: "For children over four... For children one to three years old, take two chewable tablets... under adult supervision". Pediatric dosing. **HIGH.**
11. L26-32: benefit panel repeats immune, growth and development, cognitive function, and energy. Children. **HIGH.**
12. L34-35: "formulated for children one year and older... also a multivitamin option for adults". Children. **HIGH.**
13. L37-38: "rest easy knowing your kids are getting important nutrients to support healthy growth and development". Children. **HIGH.**
- **Disclaimer:** L40-41.
- **Warnings:** L27-28 ("Keep bottle out of the reach of children") and L25 (adult supervision). **The product contains iron (L18), but the sheet has no iron accidental-overdose warning.** Check it against the physical label.

#### 10. PM-Nutritionals-ForeverMarineCollagen-US-EN-v11-051526__4_.txt (supplement, #713)
1. L8-9: "300 mg highly bioavailable collagen tripeptides". Bioavailability. MEDIUM.
2. L11-12: "Supports healthy-looking skin, hair and nails". Cosmetic/appearance. LOW.
3. L14: "Supports joint health". S/F. MEDIUM.
4. L20-21: "A scientifically advanced formula with highly bioavailable collagen tripeptides". Clinical. MEDIUM.
5. L23: "Support joint health and beauty from the inside out". S/F. MEDIUM.
6. L30: "this scientifically advanced liquid formula". Clinical. MEDIUM.
7. L34-36: "Supports skin hydration, texture and the appearance of firmer-looking skin". Appearance. LOW.
8. L34-36: tripeptides "Help support skin hydration and the appearance of youthful-looking skin". Appearance, anti-aging adjacent. LOW.
9. L38-40: "May help reduce the appearance of fine lines and wrinkles". Anti-aging claim for an ingestible product. MEDIUM.
10. L38-40: zinc "Helps promote healthy-looking skin, hair, nails and joints". S/F. MEDIUM.
11. L42-43: "Supports nail strength, hair quality and joint health". S/F. MEDIUM.
12. L43: biotin "Helps maintain skin health". S/F. MEDIUM.
13. L45-48: "Natural collagen production declines with age, making daily support an important part...". Aging-adjacent S/F. MEDIUM.
14. L50-53: "Marine collagen is more bioavailable than porcine or bovine collagen due to its smaller molecular size". Comparative/bioavailability. MEDIUM.
- **Disclaimer:** L58-59.
- **Warnings:** L24-29 (pregnancy, nursing, medical conditions, medication, a damaged sachet, keep out of reach of children). The **"For adult use only"** line quoted as label text in the guide (L94, L277-278) is **missing** here.

#### 11. PM-PersonalCare-AloeFirstSpray-US-EN-072326.txt (cosmetic, #040)
1. L5: "Helps moisturize and hydrate skin". LOW.
2. L6: "Supports skin comfort". LOW.
3. L7: "Experience the soothing sensation of aloe vera". LOW.
4. L7-9: "Leaves skin feeling calm and conditioned". LOW.
5. L9-10: "Aloe has long been used to soothe and provide moisture relief to dry, normal and combination skin". Traditional use ("relief" keyword). LOW.
6. L10: "Promotes softer, smoother-looking skin". LOW.
7. L11: "Promotes healthy-looking skin". LOW.
8. L12: "Provides skin-conditioning benefits". LOW.
9. L12-15: propolis extract "Helps soothe the skin and provides skin-conditioning benefits". LOW. The guide (L78-79) describes propolis only as "part of our botanical complex", which is a minor inconsistency.
10. L17-19 and L43: allantoin "Helps soothe the skin and promotes smoother-looking skin". LOW. Allantoin is also an OTC skin-protectant active, so check the framing.
11. L20-21: directions "Apply liberally... to soothe and moisturize. For external use only." LOW.
12. L45-47: "soothing mist great for use on skin exposed to environmental stressors". LOW (could read as sun or after-sun use).
13. L49-51: "gets to work fast". LOW.
- **Disclaimer:** cosmetic variant at L53-56.

#### 12. PM-PersonalCare-ForeverBrightToothgel-US-EN-020326__1_.txt (cosmetic oral care, #028)
1. L5: "Helps promote healthy-looking gums". Gum-health claim (gingivitis-adjacent; "looking" qualifier). MEDIUM.
2. L6: "Helps provide fresh breath". LOW.
3. L7 and L18: "Fluoride-free". OTC note: no anticavity claim and no Drug Facts, which fits a cosmetic. Review whether a fluoride-free toothgel marketed to the whole family needs added context.
4. L8: "Gentle on teeth". LOW.
5. L15: "Aloe-powered teeth cleaning for the whole family". Children (no age directions). **HIGH.**
6. L18-20: "clean teeth, fresh breath... leave your mouth feeling fresh and clean". LOW.
7. L22-23: aloe and propolis "to support your daily oral care routine". LOW.
8. L23-26: "Forever conducted years of research, collaborating with scholars and dentists to create a perfect... formula that is safe and suitable for the entire family". Clinical/expert endorsement plus children and safety. **HIGH.**
9. L19-20: directions "Brush after meals... for a healthy-looking smile". LOW.
10. L34-39: aloe and propolis each "Helps promote healthy-looking gums and helps provide fresh breath". Propolis is "used to fortify and protect their hives", an implied antimicrobial suggestion. MEDIUM.
11. L42-43: "helps support a healthy-looking smile and a clean feeling that lasts". LOW.
- **Disclaimer:** **dietary-supplement FDA text on a cosmetic** (L46-47). This is a type mismatch; flag it.
- **Warnings:** no children-under-6 or do-not-swallow directions. Flag.

#### 13. PM-SkinCare-AloeVeraGelly-US-EN-071426__1_.txt (cosmetic, #061)
1. L5-6: "Supports a smooth appearance for all skin types". LOW.
2. L8-9: "Soothes, moisturizes and conditions skin". LOW.
3. L17-18: "Soothe skin with rich aloe vera and skin-conditioning allantoin". LOW.
4. L20-21: "embraces the soothing power of aloe vera". LOW.
5. L26-28: "long been used to soothe and provide moisture relief to both dry and sensitive skin". Traditional use, "relief". LOW.
6. L21-23: directions "Thoroughly cleanse skin in area where Aloe Vera Gelly is to be applied. Apply liberally. Repeat application as needed." These mirror first-aid/wound-care directions (drug-like pattern). **MEDIUM.**
7. L37-39: aloe "Soothes and moisturizes skin"; allantoin "smooth, well-conditioned feel". LOW.
8. L41-42: "Ideal for all skin types... soothe while moisturizing and conditioning". LOW.
- **Disclaimer:** cosmetic variant at L46-49.

#### 14. PM-SkinCare-ForeverAloeLips-US-EN-070726__2_.txt (cosmetic lip, #022)
1. L5: "Moistens and softens lips". LOW.
2. L6: "Locks in moisture". LOW (protectant-adjacent).
3. L7: "Helps lips look smooth and supple". LOW.
4. L11: "helps soften, condition and soothe this delicate skin". LOW.
5. L13: "A year-round solution for lip care". LOW.
6. L14-15: "help soothe, smooth and soften your lips while providing a lasting moisture barrier". **MEDIUM.** Petrolatum is the first ingredient (L24), and "barrier" language is skin-protectant (OTC) adjacent.
7. L32-33: aloe "Helps lips feel soothed and comfortable". LOW.
8. L32-33: jojoba "Leaves lips looking supple and nourished". LOW.
9. L40-42: "the soothing power of aloe... leave your lips feeling smooth and moisturized". LOW.
- **Disclaimer:** cosmetic variant at L45-48.
- **Note:** no SPF or sunscreen claim, so no sunscreen Drug Facts are needed.

#### 15. PM_Nutritionals_-_Forever_Pro-B_Ultra_-_US_-091026__1_.txt (supplement, #710)
1. L4-5: "10 billion CFU per serving". Content. LOW.
2. L7: "Support healthy digestion and microbiome diversity". S/F. MEDIUM.
3. L8-10: "Helps promote a healthy digestive system". S/F. MEDIUM.
4. L11-13: "Helps maintain a natural balance of good bacteria". S/F. MEDIUM.
5. L11-13: "provides gut and immune support... plus additional immune support ingredients". S/F. MEDIUM.
6. L14-16: "Zinc, vitamin C and vitamin D help provide immune support". S/F. MEDIUM.
7. L15-16: "trillions of bacteria that influence digestion, nutrient absorption and immune health". S/F. MEDIUM.
8. L18-19: "helps support healthy digestion, a healthy gut microbiome, and normal immune system function". S/F. MEDIUM.
9. L20-22: "two of the most clinically studied and tested probiotic strains: Lactobacillus rhamnosus GG and Lactobacillus plantarum". Clinical. **MEDIUM.** The ImmuBlend guide (L420-422) warns that "clinically studied" can wrongly attribute someone else's research to the product.
10. L24-25: "verified for identity, potency and purity". LOW.
11. L27-28: prebiotic fiber, zinc, C and D "for immune support". S/F. MEDIUM.
12. L30-37: panel: probiotic digestion; vitamin C, zinc and D "normal immune system function"; D "maintenance of healthy bones". S/F. MEDIUM.
13. L39: "free from preservatives, added sugars and major allergens". Free-from claim. LOW.
14. L43: "Support a healthy gut microbiome with clinically studied strains". Clinical. MEDIUM.
- **Disclaimer:** L46-47.
- **Warnings:** none (no pregnancy or immunocompromised caution). Flag.

---

### Training guides

#### 16. Forever-Marine-Collagen-Training-Guide.txt (#713)
1. L7-9: "Help support joint health and beauty from the inside out with a scientifically advanced... liquid collagen". S/F and clinical. MEDIUM.
2. L31: "a scientifically advanced liquid formula". Clinical. MEDIUM.
3. L38-40: "Natural collagen production declines with age, so daily support... is an important part of a beauty and wellness routine". Aging S/F. MEDIUM.
4. L42-44: "Marine collagen is more bioavailable than porcine or bovine collagen". Comparative. MEDIUM.
5. L44-45: "Zinc, biotin & sodium hyaluronate -- support skin, hair, nail and joint health". S/F. MEDIUM.
6. L58-60: "Beauty From the Inside Out -- daily support for skin, hair, nails and joints as natural collagen declines with age". S/F. MEDIUM.
7. L77-81: key benefits: firmer-looking skin; "May help reduce the appearance of fine lines and wrinkles"; nail strength, hair quality, joint health. S/F and anti-aging. MEDIUM.
8. L82-87: tripeptides "youthful-looking skin"; zinc "healthy-looking skin, hair, nails and joints"; biotin "helps maintain skin health". S/F. MEDIUM.
9. L98-103: "Emerging research suggests these collagen-derived peptides may help support the body's natural collagen production... bioactive signals". Clinical. MEDIUM.
10. L131: "two complementary ways to support skin, hair, nails and connective tissue". S/F. MEDIUM.
11. L145-146: "helping maintain healthy-looking skin, hair, nails and joints with consistent daily use over time". S/F. MEDIUM.
12. L149-150: "sodium hyaluronate to support skin hydration". LOW.
13. L154: "an ideal form of hydrolyzed fish collagen". Superiority. MEDIUM.
14. L172-173: fruit concentrates "(antioxidants)"; "sodium hyaluronate for skin support". LOW.
15. L176-178: Dalton size "has been scientifically disproven as a way of measuring efficacy". Unsourced scientific assertion. MEDIUM.
16. L183-185: "supporting collagen levels... plays an important role in maintaining skin appearance and supporting joint health". S/F. MEDIUM.
17. L192-195: tripeptides: "Emerging research suggests they may help support the body's natural collagen production". Clinical. MEDIUM.
18. L200: "enjoy its highly concentrated benefits". LOW.
19. L204-205 (repeated at L427-428): "Collagen is broken down daily and needs support to rebuild". S/F. MEDIUM.
20. L126-127 and L209-210: "There is no daily maximum recommendation for marine collagen". Safety assertion. MEDIUM.
21. L224-225: "tested for heavy metals... meets the safety requirements set by local governmental bodies". Safety. LOW.
22. L240-247: SAY: "Supports skin hydration, texture..."; "Supports joint health with consistent daily use over time". S/F. MEDIUM.
23. L250-252: SAY: "May help support the body's natural collagen production (emerging research)". Clinical. MEDIUM.
24. L303-307: "a relatable entry point for anyone noticing changes in skin, hair, nails or joints". S/F. MEDIUM.
25. L396-398: FBO answer: "supports joint health and skin, hair and nail appearance from the inside out". S/F. MEDIUM.
26. L400-401: FBO answer to "Will it get rid of my wrinkles?": "It may help reduce the appearance of fine lines and wrinkles". Anti-aging. MEDIUM.
27. L436-440: teaching points repeat the joint, skin, fine-line and hair/nail benefits. S/F. MEDIUM.
- **Children/pregnancy (protective, not claims):** L94-98, L157-159, L277-279, L404-409 (adults only; see a healthcare professional if pregnant or nursing; "Do not recommend for anyone under adult age").
- **Disclaimer:** L447-449 and footer L460-462. The table note at L280-281 says "This product must carry this FDA disclaimer".
- **Counter-examples (AVOID):** L240-241 "Erases wrinkles"/"Makes skin younger"; L246-247 "Cures joint pain"/"Treats arthritis"; L250-252 "Proven to boost your collagen"; L260-261 "The only collagen that works"; L282-283 "Diagnoses, treats, cures, or prevents any disease".

#### 17. Forever_Absorbent-D_Training_Guide.txt (#672)
1. L5-6: "with vitamin E and enhanced absorption". Bioavailability. MEDIUM.
2. L28-29: "designed for increased vitamin D absorption". Bioavailability. MEDIUM.
3. L34-35: "Supports immune health and helps maintain strong bones with vitamin D". S/F. MEDIUM.
4. L37-39: "Studies have shown it can be difficult to get enough vitamin D through diet and sunlight alone". Clinical. MEDIUM.
5. L41-42: "Antioxidant vitamin E helps protect cells from oxidative stress". S/F. MEDIUM.
6. L44-45: "Chewable tablets offer increased vitamin D absorption". Unqualified; contrast the SAY wording "may offer" at L210. MEDIUM.
7. L52: "The easy, everyday way to fill a common vitamin D gap". Deficiency-adjacent. MEDIUM.
8. L69-74: key benefits: immune health, strong bones, nutritional gap, oxidative stress. S/F. MEDIUM.
9. L88-94: "absorbed directly by the body... fat-soluble vitamins... stored... water-soluble... eliminated through urine". Mechanism/absorption. MEDIUM.
10. L123: "supports immune health and helps maintain healthy bones". S/F. MEDIUM.
11. L141: "an additional potential benefit". LOW.
12. L146-147: "helps support immune health and helps maintain strong bones... fill this common nutritional gap". S/F. MEDIUM.
13. L150-151: absorption mechanism repeated. MEDIUM.
14. L159, L183, L324-325: "Recommended for adults 18+. For a child, seek advice from the child's medical doctor." Children-related. **MEDIUM.** It is protective, but it implies pediatric use under a doctor is possible.
15. L193-195: SAY: "Supports immune health"; "may promote a healthy immune system". S/F. MEDIUM.
16. L198-199: SAY: "Helps maintain strong bones". S/F. MEDIUM.
17. L204-207: SAY: "Helps fill a common nutritional gap". MEDIUM.
18. L209-211: SAY: "Chewable tablets may offer increased vitamin D absorption". MEDIUM.
19. L215-216: SAY: vitamin E "helps protect cells from oxidative stress". MEDIUM.
20. L248-251: example post: "Even on sunny days, getting enough vitamin D isn't always easy -- here's an easy way to help fill the gap". MEDIUM.
21. L279-280 and L291-293: social copy: vitamin E antioxidant support; "Vitamin D supports immune health and helps maintain strong bones". MEDIUM.
22. L334-336: FBO answer to "Will this cure my condition / fix my deficiency?": supports immune health and bones, and "isn't intended to diagnose, treat, cure, or prevent any disease". MEDIUM (the disclaimer sits next to the claim here).
23. L353-354: teaching point: "Immune support and bone health, plus antioxidant vitamin E for oxidative stress". MEDIUM.
- **Disclaimer:** "Always pair benefit talk with the disclaimer" at L227-230; L236; full text quoted at L364-367. **No standalone footer disclaimer.** L375-377 instead says "No... medical/disease claims have been added."
- **Counter-examples (AVOID):** L193-196 "may fight off colds and flu", "prevents you from getting sick"; L198-200 "Treats or reverses osteoporosis", "prevents bone disease"; L202-204 "Corrects your vitamin D deficiency", "treats a deficiency"; L209-211 "Absorbs better than any other vitamin D"; L213-214 "Prevents the cell damage that causes cancer and aging"; L223-225 "works instantly".

#### 18. Forever_AloeTurm_Training_Guide.txt (#676)
1. L28-29: "combines turmeric sourced from India with zinc to support immune health". S/F. MEDIUM.
2. L34-36: "Hydrogel lozenge technology -- easily dissolves and digests". LOW.
3. L35-36: "an herb with a long history of use in Ayurvedic traditions". Traditional use. LOW.
4. L41-43: "Supports immune health with the added benefit of zinc". S/F. MEDIUM.
5. L42: "Fortified with zinc -- supports immune health". S/F. MEDIUM.
6. L44-46: "Natural mint flavor -- a soothing feeling in the mouth". LOW (a "soothing" lozenge could imply sore-throat relief).
7. L52-54: "Immune Support, On the Go". S/F. MEDIUM.
8. L66-67: "Maintaining a healthy immune system is crucial... supporting immune health". S/F. MEDIUM.
9. L72-75: key benefits: immune health; "innovative hydrogel technology"; zinc "fortifies the formula to support immune health". S/F. MEDIUM.
10. L78-79: "Formulated to dissolve and digest slowly in the mouth". LOW.
11. L120: "A convenient way to support immune health". S/F. MEDIUM.
12. L147-149: "I already take other immune support products": the answer defers to a healthcare professional. LOW (protective).
13. L191-192 and L204-205: SAY: "Supports immune health..."; "Fortified with zinc to support immune health". S/F. MEDIUM.
14. L296-297: social copy: "Immune support that fits in your pocket". S/F. MEDIUM.
15. L306-307: "A portable immune-support habit that travels with you". S/F. MEDIUM.
16. L321-326: reel titled "My On-the-Go Immune Routine". S/F. MEDIUM.
17. L335-337: FBO answer: "dissolves in the mouth to support immune health". S/F. MEDIUM.
18. L343-344: "Allowing it to dissolve slowly is the ideal way to maximize the product's benefits". Efficacy. MEDIUM.
19. L349-351: "we believe it can be a great addition to an immune health routine and taken as needed". Efficacy plus dosing ("as needed" set against the up-to-4-per-day limit). MEDIUM.
20. L353-354: "Yes, it's still effective" after melting. Unsupported efficacy assertion. MEDIUM.
21. L372-373 and L377: teaching points: "support immune health"; "immune health support via the hydrogel format". MEDIUM.
- **Children (protective):** L101, L160, L363-364 (adults 18+). **No pregnancy or nursing caution anywhere in the guide.** L148-149 refers medication questions to a healthcare professional.
- **Disclaimer:** L219-222, L386-388, footer L393-395.
- **Counter-examples (AVOID):** L191-193 "Boosts your immune system / Prevents you from getting sick"; L195-197 "The only turmeric product that actually works"; L200-201 "Cures inflammation / Treats joint pain or disease"; L204-206 "Zinc cures colds / Guarantees you won't get sick".

#### 19. Forever_Aloe_First_Training_Guide.txt (cosmetic, #040R1)
1. L5-6: "A soothing, pH-balanced mist... quick hydration". LOW.
2. L35-36: "Helps moisturize and hydrate skin". LOW.
3. L38-39: "Supports skin comfort and leaves skin feeling calm and conditioned". LOW.
4. L41-42: "Promotes softer, smoother-looking, healthy-looking skin". LOW.
5. L44-45: "gets to work fast -- great for skin exposed to environmental stressors". LOW (sun-exposure adjacency).
6. L54: "the soothing power of aloe vera in a modern, no-mess spray". LOW.
7. L64-66: "soothes and supports skin comfort... skin exposed to everyday environmental stressors". LOW.
8. L71-76: key benefits: moisturize, comfort, calm, softer and healthy-looking skin, conditioning. LOW.
9. L75-76: "Allantoin: helps soothe the skin". LOW (allantoin is an OTC protectant active; check the framing).
10. L88-91: "Allantoin and a touch of propolis help soothe the skin". LOW.
11. L124-125: "designed to help soothe and moisturize skin". LOW.
12. L142-143: formula is "safe to use". Safety. LOW (the guide itself warns against "Safe for everyone" at L201-202).
13. L164-169: Q&A "Can it treat sunburn, eczema, or another skin condition?" names the diseases; the answer is protective. Disease-adjacent mention. MEDIUM.
14. L275: "A fast mist, soothed skin, no mess". LOW.
15. L292-294: "Can I use this on a sunburn?" The answer calls it a "soothing, moisturizing mist for everyday skin comfort" and refers to a professional. Disease-adjacent. MEDIUM.
16. L304-306: "Can I use it on my kids, or drink it?" No firm answer; it defers to the label and a professional. Children. **MEDIUM.**
17. L328-329: teaching point: "moisturize, hydrate, soothe, condition, and promote softer, smoother-, healthy-looking skin". LOW.
- **Pregnancy (protective):** L89-91, L164-165, L296-298.
- **Disclaimer:** cosmetic variant at L211-216, L342-345, and footer L350-352.
- **Counter-examples (AVOID):** L178 "Heals"/"repairs"; L181-182 "Eliminates irritation"/"stops pain"; L185-186 "Reduces wrinkles"/"reverses aging"; L189-191 "Treats sunburn"/"repairs sun damage"; L193-195 "Hypoallergenic"/"dermatologist-tested"; L201-202 "no side effects"; L211-213.

#### 20. Forever_Aloe_Propolis_Creme_Training_Guide.txt (cosmetic, #051)
1. L6-10: "help skin look and feel smoother, softer, and more nourished". LOW.
2. L33-35 (also L40-41, L74, L80, L119, L132, L158, L199-200, L350, L392-393): "over 70% of the formula". Quantitative formulation claim. **MEDIUM.** The footer (L417-419) says formulation percentages are internal-only and "not reflected in this guide", which is a direct internal conflict.
3. L44-45: "Moisturizes and helps condition skin, for a smoother, softer feel". LOW.
4. L46-47: "emollients that help lock in moisture on skin's surface". LOW (protectant-adjacent).
5. L47-48: "Helps maintain skin's smooth appearance and helps soothe skin". LOW.
6. L78-83: key benefits: tone and texture, moisturizes, soothes, smoother and softer. LOW.
7. L100-104: "helps lock in moisture on skin's surface and leaves skin feeling smoother". LOW.
8. L142-143: "Aloe Propolis Creme is Dermatest approved". Third-party test endorsement. MEDIUM.
9. L108, L161-162, L402: "Formulated Without Parabens" / "paraben-free... safe to use now". Free-from claim. **MEDIUM**, because the product sheet ingredient list (PM L34) includes methylparaben and propylparaben.
10. L169-172: "deeply moisturizes... help skin hold moisture". LOW.
11. L204-206 (repeated at L351-356): eczema, psoriasis, rosacea: "not a treatment... this can be part of your regular moisturizing routine alongside their guidance". Disease-adjacent (use alongside care for diagnosed conditions). **HIGH.**
12. L208-210: "Propolis is a known potential skin allergen for some people". Warning. LOW (protective).
13. L212-213: "does not test on animals... cruelty-free". LOW.
14. L237-240: SAY: "Aloe vera gently complemented with a touch of chamomile extract". LOW.
15. L242-244: SAY: "With antioxidant vitamin E and rich moisturizers". LOW.
16. L246-247: SAY: "Helps condition and smooth skin". LOW.
17. L326-327 and L339-340: social copy: "a rich, moisturizing cream for face and body"; "the best of aloe and the hive". LOW.
18. L397-398: teaching point: "moisturizes, nourishes, helps maintain skin's smooth appearance, helps soothe skin". LOW.
- **Pregnancy (protective):** L102-103, L215-216, L379-380.
- **Disclaimer:** cosmetic variant at L248-253, L410-413, and footer L415-416.
- **Extraction artifact:** the Section 7 table (L347-384) is misaligned; for example, the answer about "rejuvenate" sits next to "Is it vegan?". Check the source PDF.
- **Counter-examples (AVOID):** L225-229 "A rich blend of aloe vera and bee propolis"; L231-234 stacking "soothe", "rejuvenate" and "barrier"; L236-239 "Enhances the soothing power of aloe with chamomile"; L241-244 "Enriched with vitamins A & E"; L246-247 "protects"/"heals". **The product sheet uses the first three.**

#### 21. Forever_B12_Plus_Training_Guide.txt (#188)
1. L5-8: "help support normal energy metabolism, red blood cell production, and homocysteine levels already within the normal range". S/F. MEDIUM.
2. L30-33: same benefits, plus "especially relevant for vegans, vegetarians". S/F. MEDIUM.
3. L37-40: "Many people... don't get enough B12 without supplementation". Deficiency-adjacent. MEDIUM.
4. L38-39: "20,833% Daily Value -- a safe amount commonly found in B12 supplements". Safety. MEDIUM.
5. L45-47: "helps support normal energy metabolism, red blood cell production, and immune function". S/F. MEDIUM.
6. L49-52: "no established Tolerable Upper Intake Level (UL)". LOW.
7. L80-89: key benefits, including "Supports normal cell division" and folic acid "the body's normal development processes". S/F; pregnancy-adjacent. MEDIUM.
8. L94-102: "converts homocysteine... into methionine... especially useful for vegans, vegetarians, older adults". Mechanism/S/F. MEDIUM.
9. L111-113: "the two nutrients most connected to energy metabolism support and homocysteine balance". S/F. MEDIUM.
10. L129-130: "at meaningfully higher risk of low B12 intake". Deficiency-adjacent. MEDIUM.
11. L145-148: "Is that safe? Yes -- completely... The body absorbs what it needs and safely clears the rest". Absolute safety claim. MEDIUM. The guide itself (L378-379) says "don't improvise a safety reassurance".
12. L152-154: benefits list. S/F. MEDIUM.
13. L156-159: "research hasn't shown... extra energy boost... clearest benefit is for people who have an actual gap". Clinical/deficiency. MEDIUM.
14. L160-162: homocysteine maintenance. S/F. MEDIUM.
15. L169-171: "no dose-related safety concern has been identified for either ingredient". Safety. MEDIUM.
16. L173-176: "People taking metformin or long-term acid-reducing medications may have reduced B12 absorption... supplementation is often recommended". Drug-interaction/medical content. **HIGH.**
17. L190-192: "a daily B12 supplement a common recommendation for that dietary pattern". Deficiency-adjacent. MEDIUM.
18. L207-210: pregnancy: "folic acid at a dose within the range generally recommended for adults, but... not... a prenatal supplement". Pregnancy. **HIGH.**
19. L212-213: "folic acid at 400 mcg is well under its 1,000 mcg/day... upper limit". LOW.
20. L232-255: SAY column: homocysteine, energy metabolism, immune system, red blood cells, folic acid "needed for the body's normal development processes". S/F. MEDIUM.
21. L299-301: "who is most likely to benefit from a daily B12 source". MEDIUM.
22. L311-312: the two nutrients "help maintain homocysteine levels already within the normal range". MEDIUM.
23. L352-353: social copy: "a simple daily tablet helps close that gap". Deficiency-adjacent. MEDIUM.
24. L367-368: homocysteine is "A naturally occurring amino acid the body keeps in balance -- B12 and folic acid help with that". MEDIUM.
25. L378-381: FBO safety answer: "safely clears the rest". Safety. MEDIUM.
26. L383-385: FBO pregnancy answer: "folic acid at a generally recommended adult dose... isn't... a prenatal supplement". Pregnancy. **HIGH.**
27. L387-392: FBO answer to vegans: "people eating little or no meat, dairy, or eggs are at meaningfully higher risk of low intake". MEDIUM.
28. L405-408: FBO answer: "people taking metformin or long-term acid-reducing medications may have reduced B12 absorption". Drug interaction. **HIGH.**
29. L416-417: teaching point: "supporting normal energy metabolism, red blood cell production, and homocysteine balance". MEDIUM.
- **Pregnancy (protective):** L95-97, L207-210, L432-433. The label caution quoted at L95-97 is **not on the B12 product sheet**.
- **Disclaimer:** L406-409 ("must carries the exact FDA disclaimer", sic), L435-437, footer L439-441.
- **Counter-examples (AVOID):** L232-236 "heart", "heart function", "cardiovascular" (**the product sheet L39-40 uses "heart function"**); L238-240 "Boosts energy"; L243-246 "Fights off colds", "protects you" (**the product sheet L26 says "help protect"**); L248-250 "Prevents anemia", "treats low blood count"; L252-255 "Fetal development", "birth defect", "neural tube".

#### 22. Forever_Freedom_Training_Guide.txt (#896)
1. L7-9: "Move more freely with scientifically studied ingredients for joint support". Clinical. MEDIUM.
2. L32-33: "three scientifically studied ingredients that support joint function and mobility". Clinical. MEDIUM.
3. L40-43: "As we age, joints and connective tissues naturally change... can help maintain comfort and mobility". Aging- and pain-adjacent. MEDIUM.
4. L40-42: aloe "helps support normal digestive function and overall well being". S/F. MEDIUM.
5. L44-47: glucosamine and chondroitin "supports cartilage health, joint function, and joint lubrication". S/F. MEDIUM.
6. L49-51: MSM "helps maintain healthy joints and cartilage, contributes to joint comfort during movement". Pain-adjacent. MEDIUM.
7. L60-64: "wants to keep moving comfortably"; "helps support joint function and mobility over time". S/F. MEDIUM.
8. L73-75: "experience the benefits of aloe vera plus joint support". LOW.
9. L81-87: key benefits, including "Helps the body's natural ability to cushion joints" and "Contributes to joint comfort during movement". S/F, pain-adjacent. MEDIUM.
10. L91-98: how it works: support cartilage and lubrication, "comfort during movement... over time". S/F. MEDIUM.
11. L142-144: FAQ: "scientifically studied ingredients that support joint function and mobility". Clinical. MEDIUM.
12. L152-153: "especially great for active lifestyles, seniors, and anyone who wants to promote joint health". S/F; seniors is arthritis-adjacent targeting. MEDIUM.
13. L156-157: "Supporting your joints consistently can help maintain comfort and mobility as you age". Aging. MEDIUM.
14. L161-163: ingredient functions (digestive, cartilage, lubrication, joint comfort). S/F. MEDIUM.
15. L172-173: "Forever Move also has muscle support benefits". LOW.
16. L206-238: SAY column: joint function, cartilage, lubrication, "comfort during movement", "maintain comfort and mobility as you age". S/F. MEDIUM.
17. L258-262: "a game with grandkids... consistent daily joint support". S/F; older-adult targeting. MEDIUM.
18. L296-304: "Support That Grows With You": active lifestyles and seniors; "consistent support can help you keep feeling comfortable and mobile". S/F. MEDIUM.
19. L318-319 and L327-328: social copy: "same trusted joint support"; "supports staying active". LOW.
20. L354-367: FBO answers: supports joint function and mobility; "help support comfort and mobility"; "especially those with active lifestyles or seniors". MEDIUM.
21. L393-397: teaching points: joint function, cartilage health, joint lubrication, comfort during movement. MEDIUM.
- **Pregnancy (protective):** L105-110 and L178-180 (pregnancy, nursing, medical conditions, medication, keep out of reach of children).
- **Disclaimer:** L237-239, L404-406, footer L417-419.
- **Inconsistency:** the guide says "scientifically **studied**", but the product sheet says "scientifically **proven**" (PM L5, L20, L25).
- **Counter-examples (AVOID):** L206-207 "Fixes your joint pain"/"Cures arthritis"; L210-212 "Rebuilds your cartilage"/"Reverses cartilage damage"; L214-215 "Lubricates your joints like an oil change"; L217-219 "Eliminates joint pain"/"Guarantees pain-free movement"; L221-222 "Detoxes your body"/"Boosts your immune system"; L229-231 "Stops joint aging"/"Prevents age-related joint disease".

#### 23. Forever_ImmuBlend_Training_Guide_1.txt (#355)
1. L7-10: "A whole-body immune-support tablet". S/F. MEDIUM.
2. L32-37: "three nutrients connected to normal immune cell function... immune wellness starts in the gut, home to a large share of the body's immune tissue". S/F. MEDIUM.
3. L41-43: "Everyday exposure to germs and environmental stressors makes daily, whole-body immune support a genuinely useful habit -- not just a seasonal one". Disease-adjacent (germs, season). **HIGH.**
4. L42-49: key features: "support normal immune cell function"; "help feed and support the gut's own healthy bacteria"; "contribute antioxidant compounds". S/F. MEDIUM.
5. L59-62: "Positioned for everyday, proactive wellness support -- not for treating illness once it's already here". This implies preventive use. **HIGH.**
6. L63-67: "contains immune support, feeds the gut, and provides antioxidant compounds that contribute to immune health". S/F. MEDIUM.
7. L83-89: "Zinc is included at a level connected in clinical research to helping support normal immune cell function, with a stronger effect seen in older adults". Clinical. **MEDIUM.** It conflicts with L306-308 ("without implying... enhanced benefits for older adults").
8. L91-97: FOS and lactoferrin "support a healthy gut environment"; mushrooms "help support immune health". S/F. MEDIUM.
9. L101-111: how it works: the gut-immune link and a "whole-body approach". S/F. MEDIUM.
10. L135-137: "daily, proactive immune support... not just during the colder months". Seasonal-illness adjacent. MEDIUM.
11. L149-151: mushrooms "contribute antioxidant compounds that help support immune health". S/F. MEDIUM.
12. L159-161: "Immune cell function and healthy levels of the body's own beneficial bacteria". S/F. MEDIUM.
13. L162-164: "Will it stop me from getting sick? No supplement can guarantee that... not to prevent illness". Disease mention; protective. LOW.
14. L175-177: "Can I take it during cold and flu season, or will it help me get over a cold faster? ... suited to daily, year-round use as a proactive habit". Disease-adjacent (cold/flu named; "proactive"). **HIGH.**
15. L179-180: "no established benefit shown from taking more". LOW.
16. L231-233: SAY: "Supports immune cell function, day in and day out". S/F. MEDIUM.
17. L235-240: SAY: "Zinc is included at a level shown in clinical research to help support normal immune cell function -- with a stronger effect seen in older adults". Clinical. MEDIUM.
18. L242-246: SAY: mushroom mycelium and fruit-body extract "contribute antioxidant compounds". MEDIUM.
19. L248-250: SAY: "FOS helps feed your gut's own healthy bacteria". S/F. MEDIUM.
20. L252-256: SAY: "The gut is home to a large share of the body's immune tissue". S/F. MEDIUM.
21. L258-261: SAY: "Vitamin C and D3 are essential nutrients your body needs for normal immune function". S/F. MEDIUM.
22. L263-265: SAY: "A daily habit worth keeping up all year, especially through the colder months". Seasonal-illness adjacent. MEDIUM.
23. L277-278: "Say what the research shows: whole body immune support". Clinical. MEDIUM.
24. L297-298: explainer linking "a large share of the body's immune tissue lives in the gut" to the formula. MEDIUM.
25. L306-307: "Zinc is an essential nutrient that contributes to normal immune system function". S/F. MEDIUM.
26. L346 and L350: "year-round, proactive use"; "not a seasonal fix". Prevention-adjacent. MEDIUM.
27. L364-374: social copy: zinc, C and D3 "as the core, plus gut and antioxidant support"; "Immune Wellness Starts in the Gut". MEDIUM.
28. L399-403: FBO script: "While zinc has been studied in connection with the common cold, research does not establish that daily zinc supplementation prevents colds". Consumer-facing disease mention. **HIGH.**
29. L405-407: FBO asks whether posts can mention COVID or flu. The answer is no, plus "every product post needs the FDA disclaimer at the top, verbatim". Disease mention; protective. LOW.
30. L420-422: "the clinical studies that exist used a much higher amount than what's in this product". Clinical; an admitted substantiation gap for the mushroom ingredients. MEDIUM.
31. L430-431: teaching point: "zinc, vitamin C, and vitamin D3 as the immune-nutrient core, plus... antioxidant ingredients". MEDIUM.
- **Pregnancy (protective):** L101-103 and L197-199 (pregnant, trying to conceive, nursing). Medication questions go to a healthcare professional (L213-215, L414-415).
- **Disclaimer:** L267-272 ("verbatim"), L406 ("at the top"), L435-437, footer L454-456.
- **Cross-document conflicts with the product sheet:** a specific immune-cell percentage (guide L252-254 and L448-449 versus PM L14-16) and a cardiovascular claim (guide L258-259 and L439 versus PM L23-24 and L37-39).
- **Counter-examples (AVOID):** L231-233 "Boosts your immune system"/"protects you from getting sick"; L235-236 "Zinc will keep you from catching a cold"; L242-246 "Studied mushroom extract shown to boost immunity"; L248-250 "ImmuBlend is a probiotic"; L252-254 a specific immune-cell percentage; L258-260 "Supports heart health"/"cardiovascular function"; L263-265 COVID-19, flu, colds.

#### 24. Forever_iVision_Training_Guide.txt (#624; no product sheet in the input set)
1. L5-6: "Eye support for the digital age -- with Lutemax 2020". S/F. MEDIUM.
2. L28-31: "a breakthrough eye-health supplement... scientifically advanced ingredients... supports eyes that work extra hard under artificial blue light". Unsubstantiated superlative plus clinical. MEDIUM.
3. L34-38: "Many diets fall far short of... eye-promoting nutrients... proper nutrition is the first line of defense for supporting eye health". Protection/prevention language. **HIGH.**
4. L35-37: "Clinically studied Lutemax 2020... three key macular carotenoids needed for inner eye support". Clinical. MEDIUM.
5. L39-41: bilberry "plays a role in supporting eye wellness". Traditional use. LOW.
6. L40-42: "near-constant exposure to artificial blue light from digital devices". Context. LOW.
7. L44-46: zinc "contributes to normal vision... helps in the development and maintenance of night vision". S/F (night-vision adjacent). MEDIUM.
8. L48-50: "Helps filter blue light, support visual processing speed, and enhance glare recovery time". Performance enhancement. MEDIUM.
9. L52-54 and L59-61: "relevant to a wide range of ages"; "Relevant to teens and adults of all ages". Teens/children. **HIGH.**
10. L69-75: "complete, modern-day eye support... Clinically studied Lutemax 2020... supporting the retina and inner eye, particularly the macula". Clinical, macula (AMD-adjacent). MEDIUM.
11. L78-83: key benefits: healthy vision, blue-light filtering, visual processing speed, "Enhances glare recovery time", macular pigment. S/F. MEDIUM.
12. L89-93: "a synergistic combination that helps fight free radicals to help support the eye". S/F. MEDIUM.
13. L101-112: how it works: macular pigment "helps filter blue light and provides antioxidant support". S/F. MEDIUM.
14. L130-132: "A breakthrough eye-health supplement... including clinically studied Lutemax 2020". Clinical. MEDIUM.
15. L136-139: blue light "has been shown to potentially impact retinal structures through photo-oxidative reactions. Overexposure can lead to short-term eye strain and focusing problems". Disease-adjacent plus clinical. **HIGH.**
16. L144-147: Lutemax "help protect eyes against oxidative stress and filter harmful blue light by depositing nutrients into the macula". Protection claim. **HIGH.**
17. L151-152: vitamins "work together to fight free radicals and help support the eye". S/F. MEDIUM.
18. L156-157: bilberry "valued for everyday eye wellness". LOW.
19. L171-172: "Supports healthy vision by helping to filter blue light... enhances glare recovery time... helps maintain overall eye health". S/F. MEDIUM.
20. L178: "Take two softgels daily... to support healthy vision". S/F. MEDIUM.
21. L184: "Increased exposure to blue light may cause eye strain and fatigue and may lead to greater problems later in life". Disease-adjacent. **HIGH.**
22. L185-188: CDC screen-time figures for "children aged 8 to 10... children aged 11 to 14". Children, plus a third-party statistic to verify. **HIGH.**
23. L188-190: "Studies are showing the potential benefits of taking an eye supplement with carotenoids at a younger age, so teens and adults of all ages can find potential benefits". Clinical plus children. **HIGH.**
24. L209: SAY: "Supports healthy vision". MEDIUM.
25. L213-222: SAY: "Helps filter blue light"; "Supports visual processing speed and enhances glare recovery time"; "Helps support macular pigment". MEDIUM.
26. L225-227: SAY: "May help support healthy eye circulation and help reduce eye fatigue" (bilberry). Symptom-reduction wording that appears in no key-benefit list. **HIGH.**
27. L229-231: SAY: "Teens and adults of all ages can benefit from this formula". Teens/children. **HIGH.**
28. L233-234: SAY: "Supports eye health as part of a daily wellness routine". MEDIUM.
29. L254-261: screen-time story: "introduce Forever iVision as eye support built for exactly that lifestyle". MEDIUM.
30. L269-275: "teens and younger adults are now spending more screen hours... relevant now... across every age group". Children/teens. **HIGH.**
31. L297-303: glare recovery during "night driving, bright office lighting". Performance and safety adjacent. MEDIUM.
32. L316-317: "give them scientifically-backed support". Clinical. MEDIUM.
33. L315-316: "position iVision as help for filtering it out". MEDIUM.
34. L333-334: "Share some screen-time statistics across adults, teens, and children to show broad relevance". Children. **HIGH.**
35. L342-344: "most diets fall short of eye-promoting nutrients -- and how a daily supplement can help". MEDIUM.
36. L353-356: FBO answer: "supports healthy vision, helps filter blue light, and supports visual processing speed and glare recovery". MEDIUM.
37. L358-360: "modern screen use exposes eyes to significant blue light -- this is a simple way to help close that gap". MEDIUM.
38. L362-364: "Am I too young for this?" "Teens and adults of all ages can benefit -- children, teens, and adults all spend meaningful hours a day exposed to blue light." Children. **HIGH.**
39. L389-392 and L403: "use... 'aids'"; "Position it for every age... screen exposure now starts young". Children. **HIGH.**
- **Warnings:** **none.** There is no pregnancy, nursing, medication, age or keep-out-of-reach caution anywhere in the guide, unlike every other supplement guide. Fish-gelatin disclosure: L118, L165, L366-368.
- **Disclaimer:** L233-234, L397-399, footer L408-410.
- **Counter-examples (AVOID):** L210-211 "Restores your eyesight"/"Fixes vision problems"; L214-215 "Blocks all blue light"/"Protects you from screen damage"; L218-219 "Improves your reaction time"/"Cures glare sensitivity"; L222-223 "Reverses macular degeneration"/"Treats eye disease"; L226-227 "Eliminates eye strain"; L230-231 "Required for anyone with a phone".

---

## 3. Highest-risk statements (show the reviewer these first)

Ranked by severity, then by how widely the statement could spread (consumer-facing product sheet or FBO script) and by conflicts between documents. All are flagged for review only.

1. **iVision guide L184-190:** blue light "may lead to greater problems later in life"; CDC screen-time data for children aged 8-14; "Studies are showing the potential benefits... at a younger age". This combines disease-adjacent, clinical and children content, and the guide has no warnings.
2. **iVision guide L362-364:** FBO script "Teens and adults of all ages can benefit -- children, teens, and adults". A consumer-facing children claim.
3. **iVision guide L136-139 and L144-147:** blue light "potentially impact[s] retinal structures... eye strain and focusing problems"; Lutemax helps "protect eyes against oxidative stress and filter harmful blue light".
4. **iVision guide L225-227:** SAY "May help support healthy eye circulation and help reduce eye fatigue". Symptom reduction that appears in no key-benefit list.
5. **iVision guide L34-38, L28 and L130:** "proper nutrition is the first line of defense"; "breakthrough eye-health supplement"; "Clinically studied Lutemax 2020"; "enhances glare recovery time".
6. **iVision guide L333-334 and L403:** "Share... screen-time statistics across adults, teens, and children"; "Position it for every age... screen exposure now starts young".
7. **Kids product sheet L5-20 and L37-38:** the whole sheet targets children, including "growing bodies and minds" and "Iron contributes to normal cognitive function".
8. **Kids product sheet L22-25:** pediatric dosing for ages 1-3. There is no iron accidental-overdose warning in the sheet even though iron is listed (L18).
9. **ImmuBlend product sheet L23-24 and L37-39:** "Vitamins C and D support immune cell function and cardiovascular function". It contradicts guide L258-259 and L439.
10. **ImmuBlend product sheet L14-16:** "Science supports that approximately 70% to 80% of your body's immune cells reside in the gut". It contradicts guide L252-254 ("not traceable to a study").
11. **ImmuBlend product sheet L9 and L11-12:** "exposed to germs, bacteria and viruses"; "proven ingredients".
12. **ImmuBlend guide L175-177 and L263-265:** a cold and flu season Q&A answered with "year-round use as a proactive habit"; SAY "especially through the colder months".
13. **ImmuBlend guide L59-62 and L41-43:** "proactive... not for treating illness once it's already here"; "Everyday exposure to germs".
14. **ImmuBlend guide L399-403:** FBO script "zinc has been studied in connection with the common cold". A consumer-facing disease mention.
15. **ImmuBlend guide L83-89 and L235-240:** "shown in clinical research... stronger effect seen in older adults". It contradicts the same guide at L306-308. The mushroom research used higher doses (L420-422).
16. **B12 product sheet L39-40:** homocysteine "contributes to heart function". The B12 guide (L232-236, L421-422) says never to pair homocysteine with heart claims.
17. **B12 product sheet L26:** "Essential B vitamins to energize and help protect". The guide (L243-246) says an unqualified "protect" reads as disease prevention.
18. **B12 guide L173-176 and L405-408:** "People taking metformin or long-term acid-reducing medications may have reduced B12 absorption... supplementation is often recommended". Drug-interaction and medical content.
19. **B12 guide L207-210 and L383-385:** a folic acid and pregnancy answer ("generally recommended adult dose... not... prenatal"). Also L145-148: "Is that safe? Yes -- completely... safely clears the rest".
20. **AloeTurm product sheet L24-25 and L11-21:** "fortify your body's defenses"; "revolutionary hydrogel lozenge"; low absorption "Forever AloeTurm solves this issue". The last contradicts guide L242-244. The sheet has no 18+ or pregnancy caution.
21. **Fiber Fusion product sheet L12-14 and L30-32:** "May help ease occasional bloating and irregularity". Also L6-8, L24-25 and L35: "feeling of fullness", which is satiety- and weight-adjacent. No warnings.
22. **Aloe Propolis Creme product sheet L22-23, L26-28 and L5:** propolis creates "a natural barrier on your skin"; "helps rejuvenate"; "enhances the soothing power... with chamomile"; "Rich blend". All four are on the guide's AVOID list (L225-247). The sheet also lists parabens, while the guide says paraben-free.
23. **Aloe Propolis Creme guide L204-206 and L351-356:** eczema, psoriasis, rosacea: "this can be part of your regular moisturizing routine alongside their guidance".
24. **Forever Bright Toothgel product sheet L15 and L23-26:** "for the whole family"; "collaborating with scholars and dentists... safe and suitable for the entire family"; "healthy-looking gums" (L5). A dietary-supplement disclaimer on a cosmetic, and no child-use warnings.
25. **Forever Freedom product sheet L5-6, L20-21 and L25-27:** "scientifically **proven** ingredients" (the guide says "studied"). Also L46-48 and L23: "joint comfort during movement"; "move with comfort", which are pain-adjacent.
26. **Absorbent-D product sheet L15-16 and L5-8:** "Studies have shown..."; unqualified "increased vitamin D absorption" (guide SAY: "may offer"). The sheet has no adults-18+ statement; the guide says adults 18+ and refers children to a doctor (L159, L183).
27. **Pro-B Ultra product sheet L20-22 and L43:** "two of the most clinically studied and tested probiotic strains"; "clinically studied strains". This is a strain-level attribution to substantiate. No warnings.
28. **Marine Collagen product sheet and guide:** "May help reduce the appearance of fine lines and wrinkles" for an ingestible (PM L38-40; guide L79, L400-401); "Emerging research suggests..." (guide L98-103, L192-195); "no daily maximum recommendation" (guide L126, L209). "For adult use only" is missing from the product sheet.
29. **Aloe Vera Gelly product sheet L21-23 and Aloe Lips product sheet L14-15:** first-aid-style directions ("Thoroughly cleanse skin in area... Repeat application as needed"); "a lasting moisture barrier" with petrolatum listed first. Both are protectant/OTC-adjacent.

### Cross-cutting patterns to note for the reviewer
- **No asterisk linkage anywhere.** Supplement product sheets carry the FDA disclaimer once, at the foot of the page, away from the "Fast Facts" claims.
- **Cosmetic sheets** (Propolis Creme, Aloe First, Gelly, Aloe Lips) use "Forever makes no claim that its products cure or prevent any diseases...". The **Toothgel** instead uses the dietary-supplement FDA text.
- **Product sheets contradict their own training guides** in several places: ImmuBlend (cardiovascular; 70-80%), B12 (heart; "protect"), Propolis Creme (barrier, rejuvenate, rich blend, chamomile, parabens), AloeTurm (solves absorption), Freedom (proven versus studied), Absorbent-D (unqualified absorption; no age limit), Marine Collagen (adult-only line missing).
- **Cautions missing from product sheets** that the guides say are on the label: B12, Absorbent-D, AloeTurm, Marine Collagen (adult only). **No cautions at all** on Aloe Vera Gel, Fiber Fusion, Pro-B Ultra, Toothgel, or the iVision guide.
- **No OTC drug content found:** no fluoride (the toothgel is fluoride-free), no SPF or sunscreen claims, and no Drug Facts panels. The OTC-adjacent items are protectant/barrier wording (Propolis Creme, Aloe Lips; allantoin and petrolatum ingredients) and first-aid-style directions (Gelly).
- **Weight:** no direct weight-loss claims. The only weight-adjacent wording is satiety ("feeling of fullness") in Fiber Fusion and metabolism wording (Fiber Fusion zinc; Pro-B zinc).
