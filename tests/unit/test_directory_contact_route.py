"""Tests for the directory-contact-route guarded fallback (option C).

SPEC_C.md (coordinator-approved, 2026-09-24): on a critical validator
failure whose evidence is directory-only, keep today's unchanged
insufficient-evidence fallback and append a guarded "reach that office"
block (the record's own verbatim phone/email) copied from the ONE record
that matches a market the question explicitly names. The model's own
answer text is never delivered.

Fixtures below marked REAL are copied verbatim from
current_extractor.jsonl / ingestion-v6's International-Sponsoring-
Directory.directory.jsonl (see the coordinator's corpus study) - not only
synthetic "Label: value" records, per the spec's explicit instruction that
an earlier design rendered 0 of 15 real records because every test used
synthetic fixtures.
"""

from unittest.mock import patch

import pytest

from app.models.responses import ModelResponse
from app.orchestrator import chat_orchestrator
from app.orchestrator.chat_orchestrator import (
    AIOrchestrator,
    _explicit_directory_target_names,
    _select_directory_contact_route_record,
)
from app.response.cx_compose import compose_cx_response
from app.response.cx_render import render as cx_render
from app.response.models import ChatResponse
from app.response.outcome import ConversationOutcome, OutcomeKind
from app.retrieval.models import RetrievedDocument, RetrievalResult
from app.validation.validators.history_grounding_validator import documents_are_directory_only
from utils.directory_fields import build_directory_contact_route
from utils.validators import ChatRequest

CX_LOCALES = ("en", "fr", "es", "de", "nl", "it", "da", "fi", "no", "sr", "sv", "ru")

# --- REAL corpus fixtures, copied verbatim ---------------------------------

# current_extractor.jsonl, record_country == "Cameroon".
CAMEROON_REAL = """Welcome to Forever Cameroon!
+237 233 472 448
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Please click here for the Forever Business Owner application form. Printouts are accepted.
� Sign up online is not offered.
ORDERING PRODUCTS
� Minimum order size FBO: First order requirement can be any CC above 0.4CC. However, we
recommend 2CC at first order. There is no designated form required.
� Delivery Cost: We do not deliver products to FBO�s yet. FBO�s pick up their products directly
from the office.
� Average lead time for orders to arrive: N/A
� Payment methods accepted: MTN Mobile Money and Bank deposit.
� Local Product Centers available: No.
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: Yes.
� Grouped order possible?: No.
� Online shop +website available for foreign FBO�s?: No.
Forever Living Products Cameroon S.A.R.L.
Office & Product Center Address Santa Barbara, Route Bonamousaddi
B.P . 18246, Douala - Cameroon
Business Hours Office 08.30 am � 17.30 pm (Mon � Fri)
Business Hours Product Centre 08.30 am � 17.30 pm (Mon � Fri)
09.00 am � 13.00 pm (Sat)
Telephone Office +237 233 472 448
Telephone for Orders (see above)
Mobile +237 677 747 555
Email info@flpcameroon.com
Website www.foreverliving.com
Gabon
BONUS PAYMENT
� To local FBO�s
Monthly bank transfers if bonus amount is greater than XAF 2000 (Local currency).
� To foreign FBO�s
By cheque.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: No.
LOCAL TRAININGS
Forever Business opportunity presentation, How to start correctly, First steps to Manager, Product launch/
Product trainings."""

# current_extractor.jsonl, record_country == "Vietnam".
VIETNAM_REAL = """Welcome to Forever Vietnam!
+848 932 5076
FREQUENTLY ASKED QUESTIONS
NOTE
The Vietnamese area does not offer incoming International Sponsoring. Foreign FBO�s cannot sponsor
anybody with Vietnamese residence, nor can they have their data unlocked for Vietnam and purchase
products there.
Vietnamese FBO�s can pursue International Sponsoring in other countries.
GENERAL INFORMATION
Aloe Trading Company Ltd.
Office Address
Ms. Truong Thi Nhi Admin Office:
19C Cong Hoa, ward 12,
Tan Binh district
Hochiminh City, Vietnam
General Office
99 Nam Ky Khoi Nghia
ward 7district 3
Hochiminh City, Vietnam
Business Hours Office 09.00 am � 17.00 pm (Mon � Fri)
Telephone Office +848 939 5076, 932 5475, 932 6509
Telephone for orders See above
Fax +848 932 5928
Email atclohoi@hcm.vnn.vn
Websites www.flpvietnam.com"""

# current_extractor.jsonl, record_country == "Gabon".
GABON_REAL = """Welcome to Forever Gabon!
+241 07 46 36 77
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Please click here for the Forever Business Owner application form. Printouts are accepted.
� Sign up online is not offered.
ORDERING PRODUCTS
� Minimum order size FBO: First order requirement can be any CC above 0.4CC. However, we
recommend 2CC at first order. There is no designated form required.
� Delivery Cost: We do not deliver products to FBO�s yet. FBO�s pick up their products directly from the
office.
� Average lead time for orders to arrive: N/A
� Payment methods accepted: Bank deposit.
� Local Product Centers available: No.
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: Yes.
� Grouped order possible?: No.
� Online shop +website available for foreign FBO�s?: No.
Forever Living Products Gabon (Gabon)
Office & Product Center Address Aca�, Nomba Domaine
1386 Libreville � Gabon
Business Hours Office 09.00 am � 17.00 pm (Mon � Fri)
Business Hours Product Centre 09.00 am � 17.00 pm (Mon � Fri)
09.00 am � 13.00 pm (Sat)
Telephone Office +241 07 46 36 77 / 01 70 41 38
Telephone for Orders No orders on the phone
Mobile +241 02 17 02 73
Email info@flpcameroon.com; forevergabon@gmail.com
Website www.foreverliving.com
BONUS PAYMENT
� To local FBO�s
Monthly bank transfers if bonus amount is greater than XAF 2000 (Local currency).
� To foreign FBO�s
Monthly bank transfers if bonus amount is greater than XAF 250000 (Local currency).
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: No.
LOCAL TRAININGS
Forever Business opportunity presentation, How to start correctly, First steps to Manager, Product launch/
Product trainings."""

# current_extractor.jsonl, record_country == "Iraq". The FAQ answer to
# "Sign up with a form" begins with the word "Phone" ("Phone order is not
# available in Iraq...") and the inline field parser reads it as a SECOND
# occurrence of the canonical "phone" field alongside "Telephone Office" -
# exactly the real-corpus parsing quirk that makes the "occurs exactly
# once" rule omit Iraq's phone.
IRAQ_REAL = """Welcome to Forever Iraq!
+964 750 820 8001
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form
Phone order is not available in Iraq. FBO�s have to come or send somebody else to Arbil office in order to
place an order, make payment and pick up the products.
� Sign up online
N/A
ORDERING PRODUCTS
� Minimum order size FBO: The minimum order for new FBO�s is $100 and for FBO�s is $50.
� Delivery Cost: There is no delivery option in Iraq. Products must be picked up at the Erbil office.
� Average lead time for orders to arrive: N/A
� Payment methods accepted: Bank transfer is the only payment option. No cash or Credit Card payments.
� Local Product Centers available: Yes at the head office in Erbil.
� Online purchase by foreign FBO�s available: Via this link you can register and order, only payment
method in e-shop is to debt money to bank.
� First order required while signing up as Preferred Customer?: Yes. To be a FBO, prospects have to
provide an original and signed application form and copy of photo ID. Also first order has to be ordered.
� Grouped order possible?: N/A
� Online shop +website available for foreign FBO�s?: Via this link you can register and order, only
payment method in e-shop is to debt money to bank.
GENERAL INFORMATION
Forever Living Products Iraq
Office & Product Center Address
Building number 6 Street number
16, District Wazeeran (Next to
the TBI Bank) Erbil, Iraq
Business Hours Office 09.00 am � 17.00 pm (Sun � Thurs)
Telephone Office +964 750 820 8001
Telephone for Orders +964 750 820 8002
Email flpiraq@ymail.com
Websites www.foreverliving.com"""

# current_extractor.jsonl, record_country == "Burundi".
BURUNDI_REAL = """Welcome to Forever Burundi!
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Yes.
� Sign up online:
Yes.
ORDERING PRODUCTS
� Minimum order size FBO: $100 worth of products when joining. $50 worth of products after joining.
� Delivery Cost: $3.00 within the country.
� Average lead time for orders to arrive: 12 - 24 hours.
� Payment methods accepted: Bank deposit, Credit Card, Mobile money transfer (Mpesacam).
� Local Product Centers available: Yes.
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: Yes.
� Grouped order possible?: Not available.
� Online shop +website available for foreign FBO�s?: No.
Forever Living Products Burundi
Office & Product Center Address
Gatogato Building no. 15
(KCB Bank Compound)
1st Floor Boulevard Patrice Lumumba
Burundi
Business Hours Office 08.00 am � 17.00 pm (Mon � Fri)
Telephone Office Not available
Telephone for Orders Not available
Fax Not available
Email info@foreverea.com
Website www.foreverliving.com
BONUS PAYMENT
� To local FBO�s
Bonus paid via bank transfer ONLY when it accumulated to $5 and above. Bonus less than $5 will only be
paid after accumulating to that level.
� To foreign FBO�s
Bonus paid via bank transfer ONLY when it accumulated to $100 and above. Bonus less than $100 will
only be paid after accumulating to that level.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: No.
LOCAL TRAININGS
New FBO orientation at the FLP Training Center."""

# current_extractor.jsonl, record_country == "Ghana" (re-extracted, single country).
GHANA_REEXTRACTED_REAL = """Welcome to Forever Ghana!
+233 (0) 302 799 340
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Please click here to download the Forever Business Owner application form. Printouts are accepted.
� Sign up online:
Residents can register on www.flpgh.com.
ORDERING PRODUCTS
� Minimum order size FBO: First order requirements is US$100 +3% VAT +3% Handling charge. No
designated order form required. Price list can be downloaded on www.flpgh.com
� Delivery Cost: Not in place yet.
� Average lead time for orders to arrive: N/A
� Payment methods accepted: We accept payment in advance, slips, tellers and bank transfers.
� Local Product Centers available: Yes, in Accra, Kumasi,Takoradi and Monrovia.
Forever Living Products Ghana Ltd. Sierra Leone, Liberia
Office & Product Center Address
Number 11 Kwabena Duffour Street,
Airport Residential Area - Accra
PMB CT 251, Cantonments Accra, Ghana
Postal Address PMB CT 251, Cantonments Accra, Ghana
Business Hours Office 09.00 am � 06.00 pm (Mon � Fri)
Business Hours Product Centre 09.00 am � 06.00 pm (Mon � Fri)
09.00 am � 02.00 pm (Sat)
Telephone Office +233 (0) 302 799 340
Telephone for Orders (see above)
Fax +233 (0) 302 223 884
Email info@flpgh.com, michaelboafo@flpgh.com
Website www.foreverliving.com
www.flpgh.com
Sierra Leone, Liberia
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: Yes, a Preferred customer needs to
have a first order with an application form.
� Grouped order possible?: No.
� Online shop +website available for foreign FBO�s?: No.
BONUS PAYMENT
� To local FBO�s
Bonuses equal or above US$10 are paid by bank transfer or mobile money. FBOs without bank account
or mobile money details are paid by cheque when their bonuses are up to US$50 or above.
� To foreign FBO�s
Bonuses equal or above US$100 are paid by bank transfer. FBOs are resposible for all bank tranfer
charges. Designated form required to submit banking data. Download form at www.flpgh.com.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: No.
LOCAL TRAININGS
We have business opportunity meetings. Various FBO trainings and product trainings."""

# ingestion-v6 International-Sponsoring-Directory.directory.jsonl, the
# single record_country == "Ghana" entry, which actually merges Ghana AND
# Guinea Bissau/Conakry content into one record - each repeats its own
# "Telephone Office"/"Email" line.
GHANA_GUINEA_MERGED_V6_REAL = """Welcome to Forever Ghana!
+233 (0) 302 799 340
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Please click here to download the Forever Business Owner application form. Printouts are accepted.
� Sign up online:
Residents can register on www.flpgh.com.
ORDERING PRODUCTS
� Minimum order size FBO: First order requirements is US$100 +3% VAT +3% Handling charge. No
designated order form required. Price list can be downloaded on www.flpgh.com
� Delivery Cost: Not in place yet.
� Average lead time for orders to arrive: N/A
� Payment methods accepted: We accept payment in advance, slips, tellers and bank transfers.
� Local Product Centers available: Yes, in Accra, Kumasi,Takoradi and Monrovia.
Forever Living Products Ghana Ltd. Sierra Leone, Liberia
Office & Product Center Address
Number 11 Kwabena Duffour Street,
Airport Residential Area - Accra
PMB CT 251, Cantonments Accra, Ghana
Postal Address PMB CT 251, Cantonments Accra, Ghana
Business Hours Office 09.00 am � 06.00 pm (Mon � Fri)
Business Hours Product Centre 09.00 am � 06.00 pm (Mon � Fri)
09.00 am � 02.00 pm (Sat)
Telephone Office +233 (0) 302 799 340
Telephone for Orders (see above)
Fax +233 (0) 302 223 884
Email info@flpgh.com, michaelboafo@flpgh.com
Website www.foreverliving.com
www.flpgh.com
Sierra Leone, Liberia
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: Yes, a Preferred customer needs to
have a first order with an application form.
� Grouped order possible?: No.
� Online shop +website available for foreign FBO�s?: No.
BONUS PAYMENT
� To local FBO�s
Bonuses equal or above US$10 are paid by bank transfer or mobile money. FBOs without bank account
or mobile money details are paid by cheque when their bonuses are up to US$50 or above.
� To foreign FBO�s
Bonuses equal or above US$100 are paid by bank transfer. FBOs are resposible for all bank tranfer
charges. Designated form required to submit banking data. Download form at www.flpgh.com.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: No.
LOCAL TRAININGS
We have business opportunity meetings. Various FBO trainings and product trainings.
Welcome to Forever Guinea
Bissau and Guinea Conakry!
+224 625 80 66 70
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Please click here to download the Forever Business Owner application form. Printouts are accepted.
� Sign up online is not offered.
ORDERING PRODUCTS
� Minimum order size FBO: The minimum amount for a purchase after registering is 53.000 francs CFA.
� Delivery Cost: See fee schedule below:
2.000 francs CFA until the highway (Maristes)
3.000 francs CFA from Maristes to Thiaroye
4.000 francs CFA around Petit Mbao, Keur Mbaye Fall, Keur Massar
� Average lead time for orders to arrive: Within 1 day.
� Payment methods accepted: Cash, Card, Money Transfer.
� Local Product Centers available: Below the address of our different PC:
Guinea Bissau : Avenida Pensao Naisna Santa Luzia (+245 95 607 08 13)
Mali : SOTUBA ACI (+223 44 90 05 41)
Mauritania : Socogim Tevragh Zeina n� 155 (+222 45 29 73 79)
Guinea Conakry : Kaporo Cit� Lot 6 (+224 620 48 02 37)
The Gambia : Y2K Building Gambia Electrical Kairaba Avenue
Forever Living Products Senegal (Guinea Bissau
and Guinea Conakry)
Office Address
Kaporo Cit�
Vers les projets filets sociaux
B�timent Mitoyen au Ceci � Conakry
Business Hours Office 09.00 am � 13.30 pm (Mon � Fri)
14.00 pm � 17.30 pm (Mon � Fri)
Telephone Office +224 625 80 66 70
Telephone for Orders (see above)
Fax +221 33 820 6691
Email contact@foreversenegal.com
Websites www.foreverliving.com
Ziguinchor : Rue Javelier (+221 76 638 00 41)
Kaolack : Quartier Leona (+221 76 638 00 41)
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: Yes, the minimum value to register is
53.000 francs CFA.
� Grouped order possible?: No.
� Online shop +website available for foreign FBO�s?: No.
BONUS PAYMENT
� To local FBO�s
Bank or Money transfer.
� To foreign FBO�s
Bank or Money transfer.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: No.
LOCAL TRAININGS
Free trainings (Business and Products) are held on Monday, Wednesday, Thursday and Saturday."""

# ingestion-v6, record_country == "Kenya/East Africa".
KENYA_V6_REAL = """Welcome to Forever Kenya/East Africa!
+254 20 2026869
+254 20 2026873
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Please click here for the Forever Business Owner application form. Printouts are accepted.
� Sign up online is not offered.
ORDERING PRODUCTS
� Minimum order size FBO: $100 worth of products when joining, $50 of products after joining.
� Delivery Cost: $3 within the country.
� Average lead time for orders to arrive: 12 to 24 hours.
� Payment methods accepted: Bank deposit, Credit Card, Mobile Money Transfer (Mpesa).
� Local Product Centers available: Yes.
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: Yes.
� Grouped order possible?: Not available.
� Online shop +website available for foreign FBO�s?: No.
Forever Living Products Kenya Uganda, Tanzania, Burundi, Rwanda,
South Sudan, Ethiopia
Office & Product Center Address
Kenya Reinsurance Plaza, 4th floor
Taifa Rd. CBD, opp. High Court
Central Business District
P .O. Box 44919 - 00100
Business Hours Office 09.00 am � 19.00 pm (Mon � Fri)
10.00 am � 17.00 pm (Sat)
Telephone Office +254 20 2026869 / +254 20 2026873
Telephone for Orders +254 71 0600206
Email info@foreverea.com
Website www.foreverliving.com
Uganda, Tanzania, Burundi, Rwanda, South Sudan, Ethiopia
BONUS PAYMENT
� To local FBO�s
Bonus paid via bank transfers ONLY when it accumulated to $5 and above. Bonus less than $5 will only
be paid after accumulating to that level.
� To foreign FBO�s
Bonus paid via bank transfers ONLY when it accumulated to $100 and above. Bonus less than $100 will
only be paid after accumulating to that level.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: A tax identification number is required.
LOCAL TRAININGS
New FBO Orientation at the FLP Training Center."""

# current_extractor.jsonl, record_country == "Thailand". "Email" is a
# standalone label followed by one address per line, then a PLURAL
# "Websites" line _FIELD_LABEL_RE does not recognize as a label (only the
# singular "website" matches), so the value run keeps consuming FAQ/legal
# prose all the way to the next recognized label - about 2,000 characters,
# ending mid-sentence in the real record (Fable review 2026-09-24, B1).
THAILAND_REAL = """Welcome to Forever Thailand!
+662 258 0842-3
FREQUENTLY ASKED QUESTIONS
SIGNING UP
Sign up with a form or online
� Please register on website to access the Download area on https://shop.foreverliving.co.th to download
the FBO application form in English and Thai. Printouts are accepted. Applicant need to sign.
� Sign up online at this link https://shop.foreverliving.co.th/en/register
ORDERING PRODUCTS
Order online on web store; https://shop.foreverliving.co.th/
or via LINE application; https://line.me/R/ti/p/@foreverthailand
� Minimum order size FBO: There is no first order minimum requirement. A designated order form is not
generally required but may be asked by staff under certain circumstances. Access the download area for
latest price list, product brochure and other marketing tools.
� Delivery Cost: Depends on the size of the order by weight. Free domestic delivery for orders above
2,000 Thai Baht.
� Average lead time for orders to arrive: Orders typically take 1 to 2 working days outside of Bangkok.
GENERAL INFORMATION
Forever Living Products Thailand Co., Ltd.
Office & Product Center Address
Bangkok Product Centre
Unit 3923, 9th Floor, BB Building
54 Sukhumvit Soi (Asoke) Road, Bangkok, 10110
Thailand
Business Hours Office 10:00 am � 18:00 pm (Mon � Fri)
Closed weekends and Bank Holidays
Telephone Office +662 258 0842-3
Telephone for orders +662 258 0842-3
+669 4216 9648 (WhatsApp)
Fax +662 258 0843
Email
info@foreverliving.co.th (General inquiries)
orders@foreverliving.co.th (Orders)
support@foreverliving.co.th (FBO support)
Websites www.foreverliving.co.th
In Bangkok next day delivery is generally offered depending on area and if order is placed before 2pm.
Same day delivery is offered at extra charge.
� Payment methods accepted: Cash and credit cards if ordering at the product center. Credit cards, bank
transfer and cash payment at local convenience store are accepted when placing an order on web store.
� Local Product Centers available: Bangkok Product center and any of our meeting venues.
� Online purchase by foreign FBO�s available: Yes, foreign and local FBO�s can purchase online at
https://shop.foreverliving.co.th once they have registered as users on Web Store. In order to do this FBOs
need to be internationally sponsored into Thailand.
� First order required while signing up as Preferred Customer?: No.
� Grouped order possible?: No, each FBO gets a separate invoice per transaction under their name and
their corresponding ID number.
� Online shop +website available for foreign FBO�s?: Yes.
BONUS PAYMENT
� Bank transfer. The costs of payment via International Bank transfer is deducted from commissions.
Costs varies according to the amount transferred and the recipient�s country.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: In Thailand only companies can be VAT registered unless an individual�s annual
turnover exceeds the 1.8 million Baht threshold (approx. 58k US$). Thai domestic distributors cannot
register as an FBO business entity, we do however honor foreign FBO�s registered as a business entity.
Link to the Thai Revenue Dept.: www.rd.go.th/publish/6043.0.html
� Social security registration: The 13 digit Thai National ID card is required when Thai nationals apply for
a FBOship. For foreigners passport info is needed. Thailand requires for withholding tax to be withheld by
the payer and paid to the Revenue Department on their behalf. National and foreign residents are taxed
different rates according to double taxation treaties in existence with their country of residence.
� Other registrations: No other known.
LOCAL TRAININGS
Follow our social media channels for business meeting announcements, which can be physical, hybrid or
online only meetings.
Facebook: https://www.facebook.com/foreverthailandhq
Instagram: https://www.instagram.com/foreverlivingth/
YouTube: https://www.youtube.com/c/foreverlivingthailandhq"""

# current_extractor.jsonl, record_country == "Bosnia & Herzegovina". Same
# shape as Thailand: "Email" alone, one address per line, then a plural
# "Websites" line and bonus/legal prose absorbed into the value.
BOSNIA_HERZEGOVINA_REAL = """Welcome to Forever Bosnia & Herzegovina!
+387 55 211 784
GENERAL INFORMATION
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Printed forms are available in our Product Center.
� Sign up online:
On-going introduction
ORDERING PRODUCTS
� Minimum order size FBO: �55,00 +17% VAT
� Delivery Cost: This is determined by the weight of the order and the location it needs to be delivered to.
� Average lead time for orders to arrive: Normal delivery time is 24 to 48 hours.
� Payment methods accepted: Credit Card and wire transfer to our bank accounts.
� Local Product Centers available: Yes: FLP Bosnia & Herzegovina, FLP Sarajevo Dzemala Bijedica
166A, 71000 Sarajevo.
� Online purchase by foreign FBO�s available: -
� First order required while signing up as Preferred Customer?: Yes, first order goes with an application
form.
� Grouped order possible?: Yes.
� Online shop +website available for foreign FBO�s?: In setup process at the moment
BONUS PAYMENT
Forever Living Products Hungary (Bosnia &
Herzegovina)
Office & Product Center Address Trg Djenerala Draze 3
763000 Bijeljina, Bosnia & Herzegovina
Business Hours Office 09.00 am � 17.00 pm (Mon � Fri)
Telephone Office +387 55 211 784
Telephone for Orders +387 55 211 784
Email
flpbos@teol.net
forever.flpbos@gmail.com
flpbosniacustomercare@gmail.com
Websites www.flpshop.ba
� To local FBO�s
Domestic bonuses are paid by bank transfer. Income tax and contribution for pension security are
deducted. FBO�s registered as companies send their companies invoices.
� To foreign FBO�s
Head office, Forever Living Products Hungary pays foreign FBO�s, we have mutual compensation bonus
agreement in our group.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: Not necessary for private persons, for entrepreneurships above certain level
� Social security registration: -
� Other registrations: Personal Identification number
LOCAL TRAININGS
Yes, the training is given by managers in the business. OTS (online training system), free access to Webinar
platform, public presentations."""

# current_extractor.jsonl, record_country == "Nigeria". Trailing-comma
# regression guard (Fable review 2026-09-24, B1 fix-up): the real inline
# "Email" value is "flphelpdesk@yahoo.com, info@flpng.com," - a bare
# trailing comma with nothing after it on that line (the next line,
# "flpngmarketing@gmail.com", is not itself part of this value: it follows
# an INLINE match, which consumes only its own line).
NIGERIA_REAL = """Welcome to Forever Nigeria!
+234 1 2711795
FREQUENTLY ASKED QUESTIONS
SIGNING UP
� Sign up with a form:
Forever Business Owner application forms need to be supplied by the office as they have been produced
in the print shop. No printouts of the form nor copies of any kind of the signed form are accepted.
� Sign up online:
Residents of Nigeria can register online.
ORDERING PRODUCTS
� Minimum order size FBO: The first order requirement is USD304,15 including VAT. No designated order
form required. Price list can be downloaded from here under DOWNLOADS, no password required.
� Delivery Cost: The minimum order must be the Naira equivalent of $52,50.
� Average lead time for orders to arrive: Business owners are responsible for the collection and
transportation of their products to various destinations.
� Payment methods accepted: Foreverliving.com accepts Visa, MasterCard, Discover card or Money
Orders. The money order must be received at the home office before your product will be shipped. During
GENERAL INFORMATION
Forever Living Products Nigeria (Limited)
Office & Product Centre Address
The Forever Complex
21/23 Aromire Avenue
Off Adeniyi Jones Avenue
Ikeja, Lagos State
Business Hours Office 08.30 am � 17.00 pm (Mon � Fri)
Business Hours Product Centre 08.30 am � 17.00 pm (Mon � Fri)
Telephone Office +234 1 2711795
Telephone for Orders (see above)
Fax +234 1493 7895
Email flphelpdesk@yahoo.com, info@flpng.com,
flpngmarketing@gmail.com
Websites www.foreverliving.com
the checkout process, you will be prompted to enter your credit card information.
� Local Product Centers available: We have 5 Product Center. Contact Nigeria Office +234-1-2711795
for more information on the location and hours of each Product Centre.
� Online purchase by foreign FBO�s available: No.
� First order required while signing up as Preferred Customer?: No.
� Grouped order possible?: No.
� Online shop +website available for foreign FBO�s?: No.
BONUS PAYMENT
� To local FBO�s
Bonuses are paid into Nigerian bank accounts only.
� To foreign FBO�s
See above.
LEGAL REQUIREMENTS AS FBO, OTHER THAN NORMAL INCOME TAXATION
� VAT Registration: No.
� Social security registration: No.
� Other registrations: No.
LOCAL TRAININGS
Training for all our centers can be found online.
The Business Presentation dates can be found online."""


def _record_doc(
    record_country, content, *, section="sponsoring", kind="international_sponsoring", country="GLOBAL",
    doc_id="rec-1",
):
    metadata = {"document_type": "office_directory", "directory_section": section, "record_country": record_country}
    if kind:
        metadata["directory_kind"] = kind
    return RetrievedDocument(
        id=doc_id, title=record_country, content=content, source=f"s3://kb/{doc_id}",
        country=country, language="en", score=0.8, metadata=metadata,
    )


# --- build_directory_contact_route: real-record field guards ---------------


def test_cameroon_real_record_renders_phone_and_never_see_above() -> None:
    block = build_directory_contact_route(CAMEROON_REAL, "en")
    assert block is not None
    assert "+237 233 472 448" in block
    assert "see above" not in block.lower()


def test_vietnam_real_record_note_text_never_appears_in_the_block() -> None:
    block = build_directory_contact_route(VIETNAM_REAL, "en")
    assert block is not None
    assert "does not offer incoming" not in block
    assert "Vietnamese FBO" not in block


def test_gabon_real_record_never_renders_the_order_phone() -> None:
    block = build_directory_contact_route(GABON_REAL, "en")
    assert block is not None
    assert "No orders on the phone" not in block
    assert "+241 07 46 36 77" in block


def test_iraq_real_record_renders_email_only() -> None:
    block = build_directory_contact_route(IRAQ_REAL, "en")
    assert block is not None
    assert "flpiraq@ymail.com" in block
    assert "Phone" not in block
    assert "not available in Iraq" not in block


def test_burundi_real_record_not_available_renders_no_phone() -> None:
    block = build_directory_contact_route(BURUNDI_REAL, "en")
    assert block is not None
    assert "Phone" not in block
    assert "Not available" not in block


def test_ghana_guinea_merged_v6_record_renders_no_block() -> None:
    assert build_directory_contact_route(GHANA_GUINEA_MERGED_V6_REAL, "en") is None


def test_reextracted_ghana_record_renders_its_own_phone() -> None:
    block = build_directory_contact_route(GHANA_REEXTRACTED_REAL, "en")
    assert block is not None
    assert "+233 (0) 302 799 340" in block


# --- B1 (BLOCKING, Fable review 2026-09-24): email blob guard --------------


def test_thailand_real_record_renders_phone_only_no_email_no_prose_leak() -> None:
    """The real "Email" value run swallows ~2,000 chars of FAQ/legal prose
    (the plural "Websites" line is not a recognized label) - the email must
    be omitted entirely, and none of that prose may appear anywhere in the
    block. The phone still renders."""
    block = build_directory_contact_route(THAILAND_REAL, "en")
    assert block == "- Phone: +662 258 0842-3"
    assert "Email" not in block
    assert "General inquiries" not in block
    assert "Websites" not in block
    assert "withholding tax" not in block
    assert "Bangkok" not in block


def test_bosnia_herzegovina_real_record_omits_email_keeps_phone() -> None:
    """Same real shape as Thailand. The market name does not resolve
    through _explicit_directory_target_names today (the "&" segment), so
    this is tested directly against build_directory_contact_route rather
    than through record selection."""
    block = build_directory_contact_route(BOSNIA_HERZEGOVINA_REAL, "en")
    assert block == "- Phone: +387 55 211 784"
    assert "Email" not in block
    assert "flpbos@teol.net" not in block
    assert "Domestic bonuses" not in block


def test_nigeria_real_record_still_renders_its_trailing_comma_email() -> None:
    """Regression guard for the B1 fix-up: a value ending in a bare
    trailing "," (nothing after it on that line) must still render once the
    trailing separator is stripped before the safety check, not just before
    display."""
    block = build_directory_contact_route(NIGERIA_REAL, "en")
    assert block == "- Phone: +234 1 2711795\n- Email: flphelpdesk@yahoo.com, info@flpng.com"


# --- Delta hardening 3 (Fable review 2026-09-25): strict dotted-domain email


def test_email_with_a_trailing_parenthetical_caveat_is_rejected() -> None:
    """The <=40-char parenthetical allowance is removed entirely - a
    caveat like "(sponsoring closed, use home office)" is no longer a
    permitted trailer at all."""
    content = "Kenya/East Africa Office\nTelephone: +254 20 2721133\n" \
        "Email: info@kenya.example (sponsoring closed, use home office)"
    block = build_directory_contact_route(content, "en")
    assert block == "- Phone: +254 20 2721133"


def test_email_with_a_triangular_bullet_glued_to_prose_is_rejected() -> None:
    """A bullet character other than the originally-banned "•" (here
    "‣") is still rejected - not by the banned-substring list, but
    because it falls outside the closed token/separator character set the
    whole-value regex matches end to end."""
    content = "Kenya/East Africa Office\nTelephone: +254 20 2721133\n" \
        "Email: info@kenya.example‣Bonuses are paid monthly."
    block = build_directory_contact_route(content, "en")
    assert block == "- Phone: +254 20 2721133"


def test_email_with_a_zero_width_character_is_rejected() -> None:
    """A zero-width space (U+200B) embedded in the value fits neither the
    token nor the separator character class, so the whole-value regex
    fails to match - no separate check is needed for it."""
    content = "Kenya/East Africa Office\nTelephone: +254 20 2721133\n" \
        "Email: info@kenya.example​, ops@kenya.example"
    block = build_directory_contact_route(content, "en")
    assert block == "- Phone: +254 20 2721133"


def test_email_with_a_fake_caveat_subdomain_is_accepted_as_a_known_limitation() -> None:
    """Documented, accepted gap: this guard authenticates the SHAPE of an
    email address, not the intent behind its domain labels. A value like
    "info@kenya.example.closed.do.not.sponsor.here" is a syntactically
    valid multi-label dotted domain and is accepted (Fable review,
    2026-09-25)."""
    content = "Kenya/East Africa Office\nTelephone: +254 20 2721133\n" \
        "Email: info@kenya.example.closed.do.not.sponsor.here"
    block = build_directory_contact_route(content, "en")
    assert block == (
        "- Phone: +254 20 2721133\n- Email: info@kenya.example.closed.do.not.sponsor.here"
    )


def test_staff_record_own_labels_do_not_match_the_canonical_phone_or_email_pattern() -> None:
    # Staff records are excluded from selection entirely by
    # _select_directory_contact_route_record's directory_section == "staff"
    # guard (see below); this only documents that a staff record's own
    # "Main Admin Cell#"/"Main Admin. Email" labels are compound labels that
    # do not match the canonical phone/email patterns either way, so a
    # staff record never renders a block even if it were not excluded.
    staff_content = (
        "Kenya - Emmanuel Akwiri\nOperating Country\nKenya\nMain Admin Cell#\n254 720 701 731\n"
        "Main Admin. Email\neakwiri@foreverea.com"
    )
    assert build_directory_contact_route(staff_content, "en") is None


@pytest.mark.parametrize("language", CX_LOCALES)
def test_all_12_cx_locales_render_a_labelled_block(language) -> None:
    block = build_directory_contact_route(CAMEROON_REAL, language)
    assert block is not None
    assert "+237 233 472 448" in block
    assert "{" not in block and "}" not in block


@pytest.mark.parametrize("language", ("pt", "nb", "nn", "xx"))
def test_unconfigured_and_aliased_locales_never_call_localize_reviewed_copy(language) -> None:
    with patch("services.controlled_copy.localize_reviewed_copy") as mocked:
        block = build_directory_contact_route(CAMEROON_REAL, language)
    assert mocked.call_count == 0
    assert block is not None


# --- N3 (Fable review 2026-09-24): the note's own configured-locale guard --


def test_directory_contact_route_locale_is_configured_matches_the_12_cx_locales() -> None:
    from utils.directory_fields import directory_contact_route_locale_is_configured

    for language in CX_LOCALES:
        assert directory_contact_route_locale_is_configured(language) is True
    for language in ("pt", "xx"):
        assert directory_contact_route_locale_is_configured(language) is False
    for language in ("nb", "nn"):
        assert directory_contact_route_locale_is_configured(language) is True


def test_nb_and_nn_alias_to_the_reviewed_norwegian_labels() -> None:
    for language in ("nb", "nn"):
        block = build_directory_contact_route(CAMEROON_REAL, language)
        assert block is not None
        assert "Telefon" in block


# --- Adversarial: caveat/note text is never absorbed into a field value ----


def test_kenya_note_line_inverting_meaning_is_never_part_of_the_phone_value() -> None:
    content = (
        "Kenya/East Africa Office\nTelephone: +254 20 2721133\n"
        "Note: This office does not accept new sponsoring applications."
    )
    block = build_directory_contact_route(content, "en")
    assert block == "- Phone: +254 20 2721133"


@pytest.mark.parametrize(
    "content",
    [
        "Kenya/East Africa Office\nTelephone Office: +254 20 2721133\n"
        "Not accepting new sponsoring applications at this office",
        "Welcome to Forever Kenya/East Africa!\nTelephone Office: +254 20 2721133\n"
        "Sponsoring desk temporarily closed - please use your home office contact",
    ],
)
def test_kenya_caveat_lines_never_appear_in_the_rendered_block(content) -> None:
    block = build_directory_contact_route(content, "en")
    assert block == "- Phone: +254 20 2721133"
    assert "sponsoring" not in block.lower()
    assert "office" not in block.lower()


def test_two_phone_occurrences_omit_the_phone_field_entirely() -> None:
    content = "Kenya/East Africa Office\nPhone 1: +254 20 2721133\nPhone 2: +254 20 9999999"
    assert build_directory_contact_route(content, "en") is None


def test_heading_that_reads_like_a_caveat_does_not_block_a_real_phone_field() -> None:
    content = "Not accepting sponsoring applications until further notice\nTelephone: +254 20 2721133"
    assert build_directory_contact_route(content, "en") == "- Phone: +254 20 2721133"


# --- Record selection: market-safe, no session fallback --------------------


def test_kenya_question_with_only_a_ghana_record_selects_nothing() -> None:
    ghana_doc = _record_doc("Ghana", "Forever Ghana\nTelephone Office: +233 30 1234567\nEmail: info@foreverghana.test")
    assert _select_directory_contact_route_record([ghana_doc], "What is the Kenya office phone number?") is None


def test_finnish_kenian_question_with_ghana_only_record_selects_nothing() -> None:
    ghana_doc = _record_doc("Ghana", "Forever Ghana\nTelephone Office: +233 30 1234567")
    assert _select_directory_contact_route_record(ghana_doc and [ghana_doc], "Mikä on Kenian toimiston puhelinnumero?") is None


def test_finnish_kenian_question_never_falls_back_to_the_session_record() -> None:
    finland_doc = _record_doc("Finland", "Forever Finland\nTelephone Office: +358 9 1234567")
    assert _select_directory_contact_route_record([finland_doc], "Mikä on Kenian toimiston puhelinnumero?") is None


def test_russian_inflected_kenii_resolves_no_market_today() -> None:
    kenya_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL)
    assert _select_directory_contact_route_record([kenya_doc], "Какой номер телефона офиса в Кении?") is None


def test_two_named_markets_with_both_records_select_neither() -> None:
    kenya_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL, doc_id="ke")
    ghana_doc = _record_doc("Ghana", GHANA_REEXTRACTED_REAL, doc_id="gh")
    selected = _select_directory_contact_route_record(
        [kenya_doc, ghana_doc], "Phone numbers for the Kenya and Ghana offices?"
    )
    assert selected is None


def test_kenya_office_record_is_never_a_candidate_so_only_sponsoring_is_selected() -> None:
    """N1 (Fable review, 2026-09-24): the positive allowlist excludes an
    office record from candidacy entirely - it can no longer make an
    otherwise-unambiguous sponsoring match "ambiguous" the way the old
    denylist did."""
    sponsoring = _record_doc("Kenya/East Africa", KENYA_V6_REAL, doc_id="sponsoring")
    office = _record_doc(
        "KENYA (East Africa)",
        "KENYA (East Africa) - FLP\nCountry\nKENYA (East Africa)\nOffice Phone 1\n254 20 273 7800",
        section="office", kind=None, doc_id="office",
    )
    selected = _select_directory_contact_route_record([sponsoring, office], "What is the Kenya office phone number?")
    assert selected is sponsoring


def test_staff_record_is_never_selected() -> None:
    staff = _record_doc(
        "Kenya",
        "Kenya - Emmanuel Akwiri\nOperating Country\nKenya\nMain Admin Cell#\n254 720 701 731\n"
        "Main Admin. Email\neakwiri@foreverea.com",
        section="staff", kind=None, doc_id="staff",
    )
    assert _select_directory_contact_route_record([staff], "What is the Kenya contact phone?") is None


# --- N1 (Fable review 2026-09-24): positive allowlist, case-insensitive ---


@pytest.mark.parametrize("section", ["staff", "Staff", "STAFF", " staff "])
def test_staff_shaped_record_is_excluded_for_every_casing_and_whitespace(section) -> None:
    staff_doc = _record_doc(
        "Kenya",
        "Kenya - Emmanuel Akwiri\nCountry\nKenya\nPhone\n+254 720 701 731\nEmail\neakwiri@foreverea.com",
        section=section, kind=None, doc_id="staff",
    )
    assert _select_directory_contact_route_record([staff_doc], "What is the Kenya contact phone?") is None


def test_missing_section_with_canonical_labels_is_never_a_candidate() -> None:
    """A record with no directory_section and no directory_kind at all -
    even one carrying canonical Phone/Email labels - must never be treated
    as a sponsoring candidate."""
    doc = _record_doc(
        "Kenya",
        "Kenya - Emmanuel Akwiri\nCountry\nKenya\nPhone\n+254 720 701 731\nEmail\neakwiri@foreverea.com",
        section=None, kind=None, doc_id="unlabeled",
    )
    assert _select_directory_contact_route_record([doc], "What is the Kenya contact phone?") is None


# --- N2 (Fable review 2026-09-24): two distinct named markets -------------


def test_two_distinct_markets_named_with_only_one_record_retrieved_selects_nothing() -> None:
    kenya_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL)
    selected = _select_directory_contact_route_record(
        [kenya_doc], "Is the Kenya office phone the same as the Uganda one?"
    )
    assert selected is None


def test_ghana_only_follow_up_after_a_kenya_turn_still_resolves_to_ghana() -> None:
    """A single named market must keep working even though N2's gate looks
    at find_market_mentions directly - "What about Ghana?" names one
    market, not two."""
    ghana_doc = _record_doc("Ghana", GHANA_REEXTRACTED_REAL)
    selected = _select_directory_contact_route_record([ghana_doc], "What about Ghana?")
    assert selected is ghana_doc


def test_a_single_market_expanding_to_two_alias_names_still_selects() -> None:
    """N2 must not regress a single-market framing where a shared-office
    alias contributes a target name distinct from the market's own -
    "Martinique" resolves to ["Martinique", "St. Maarten"] from ONE named
    market, not two, and must still render."""
    st_maarten_doc = _record_doc("St. Maarten", "Welcome to Forever St. Maarten!\nTelephone Office: +33 170 392 222")
    selected = _select_directory_contact_route_record(
        [st_maarten_doc], "What is the Martinique office phone number?"
    )
    assert selected is st_maarten_doc


def test_exactly_one_kenya_match_is_selected() -> None:
    kenya_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL)
    selected = _select_directory_contact_route_record(
        [kenya_doc], "Who is the sponsoring contact for Kenya, and what is their phone number?"
    )
    assert selected is kenya_doc


def test_explicit_directory_target_names_is_empty_with_no_market_named() -> None:
    assert _explicit_directory_target_names("What are your business hours?") == []


# --- documents_are_directory_only public helper -----------------------------


def test_documents_are_directory_only_true_for_a_single_directory_record() -> None:
    kenya_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL)
    assert documents_are_directory_only([kenya_doc]) is True


def test_documents_are_directory_only_false_when_any_document_is_not_directory_shaped() -> None:
    kenya_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL)
    policy_doc = RetrievedDocument(
        id="policy-1", title="Policy", content="Section 6.02", source="s3://kb/policy-1",
        country="US", language="en", score=0.9, metadata={"section_id": "6.02"},
    )
    assert documents_are_directory_only([kenya_doc, policy_doc]) is False


# --- End-to-end: AIOrchestrator._validate_response --------------------------


def _critical_fallback_response(orchestrator, body, model_text, record_doc):
    model_response = ModelResponse(text=model_text, citations=[], confidence=0.9, provider="claude", model_name="m")
    chat_response = ChatResponse(
        answer=model_text, citations=[], suggestions=[], cards=[], confidence=0.8,
        metadata={"response_source": "model"}, correlation_id="test",
    )
    retrieval_result = RetrievalResult([record_doc], [], 0.8)
    return orchestrator._validate_response(
        chat_response, body, "test",
        model_response=model_response, retrieval_result=retrieval_result,
        directory_contact_route=True, lookup_text=body.message,
    )


@pytest.fixture(autouse=True)
def _offline_scrub_pii(monkeypatch):
    """No network: scrub_pii is stubbed to the identity function everywhere
    in this file, matching the established pattern in test_chat_orchestrator.py.
    """
    monkeypatch.setattr(chat_orchestrator, "scrub_pii", lambda text, *_, **__: text)


def test_rejection1_note_inverting_meaning_never_appears_in_the_delivered_answer() -> None:
    """REJ1: the model's answer states the office DOES accept applications
    and is unavailable; none of that sentence may reach the reader."""
    orchestrator = AIOrchestrator()
    body = ChatRequest(
        message="Can I apply for sponsoring in Kenya, and what is the phone?",
        sessionId="s1", country="US", language="en",
    )
    model_text = (
        "You can apply for sponsoring through the Kenya/East Africa office telephone "
        "+254 20 2721133. Please be aware that it currently is not taking on any fresh "
        "applicants for sponsorship."
    )
    record_doc = _record_doc(
        "Kenya/East Africa",
        "Welcome to Forever Kenya/East Africa!\nTelephone Office: +254 20 2721133\n"
        "Note: This office does not accept new sponsoring applications.\nEmail: info@foreverea.com\n",
    )
    delivered = _critical_fallback_response(orchestrator, body, model_text, record_doc)

    assert "You can apply" not in delivered.answer
    assert "not taking on any fresh applicants" not in delivered.answer
    assert "+254 20 2721133" in delivered.answer
    assert delivered.metadata.get("directory_contact_route") == {
        "record_id": "rec-1", "record_country": "Kenya/East Africa", "labels": ["Phone", "Email"],
    }
    assert delivered.citations == [
        {
            "title": "Kenya/East Africa", "uri": "s3://kb/rec-1", "excerpt": "", "page": "",
            "documentVersion": "", "country": "GLOBAL", "language": "en", "score": 0.8,
            "supportContactSupplement": True,
        }
    ]


@pytest.mark.parametrize(
    "language,question",
    [
        ("en", "Who is the sponsoring contact for Kenya, and what is their phone number?"),
        ("it", "Chi e il contatto di sponsorizzazione per il Kenya, e qual e il suo numero di telefono?"),
        ("no", "Hvem er sponsorkontakten for Kenya, og hva er telefonnummeret deres?"),
    ],
)
def test_live_shapes_cx_04_show_the_kenya_phone_and_email(language, question) -> None:
    orchestrator = AIOrchestrator()
    body = ChatRequest(message=question, sessionId="s1", country="US", language=language)
    model_text = "The Kenya sponsoring office previously told me their hours changed last month."
    record_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL)
    delivered = _critical_fallback_response(orchestrator, body, model_text, record_doc)

    assert "+254 20 2026869" in delivered.answer
    assert "info@foreverea.com" in delivered.answer
    assert "hours changed last month" not in delivered.answer


def test_live_shape_cx_11b_ghana_reextracted_record_renders_its_phone() -> None:
    orchestrator = AIOrchestrator()
    body = ChatRequest(message="No, quise decir Ghana.", sessionId="s1", country="US", language="es")
    model_text = (
        "The Ghana office previously mentioned they extended their weekend hours to 9pm and now "
        "offer free same-day delivery within Accra for every order."
    )
    record_doc = _record_doc("Ghana", GHANA_REEXTRACTED_REAL)
    delivered = _critical_fallback_response(orchestrator, body, model_text, record_doc)

    assert "+233 (0) 302 799 340" in delivered.answer


def test_live_shape_r10_01_tanzania_mismatch_keeps_the_plain_fallback() -> None:
    """A question about "Tanzania" cannot self-match a record filed as
    "Tanzania, United Republic of" - no block, plain fallback only."""
    orchestrator = AIOrchestrator()
    body = ChatRequest(
        message="And what about FBOs who live there, in Tanzania itself?",
        sessionId="s1", country="US", language="en",
    )
    model_text = (
        "History said the Tanzania office extended its hours last quarter and waived delivery fees "
        "for every FBO ordering more than two cases a month."
    )
    # The real corpus files this record under the bare "Tanzania" - not the
    # "Tanzania, United Republic of" name find_market_mentions/
    # market_display_name resolves for the question below - so the market
    # match fails today (see proto_c.py's own measured self-match failure).
    record_doc = _record_doc("Tanzania", "Welcome to Forever Tanzania!\nTelephone Office: +255 22 1234567")
    delivered = _critical_fallback_response(orchestrator, body, model_text, record_doc)

    assert delivered.metadata.get("directory_contact_route") is None
    assert "+255 22 1234567" not in delivered.answer
    assert "History said something" not in delivered.answer


def _kenya_history_leak_case(orchestrator, language):
    # ChatRequest's own pydantic validator only accepts the platform's
    # supported language codes, which excludes "pt"/"xx" (and "nb" is not
    # itself a body.language value the API accepts either) - so the target
    # answer language is set the same way the real pipeline sets one that
    # differs from the request's own (_answer_language reads the
    # _ANSWER_LANGUAGE contextvar first), rather than through body.language.
    body = ChatRequest(
        message="Who is the sponsoring contact for Kenya, and what is their phone number?",
        sessionId="s1", country="US", language="en",
    )
    model_text = (
        "History said the Kenya sponsoring office extended their hours last month and waived the "
        "delivery fee for every order over three case credits."
    )
    record_doc = _record_doc("Kenya/East Africa", KENYA_V6_REAL)
    token = chat_orchestrator._ANSWER_LANGUAGE.set(language)
    try:
        return _critical_fallback_response(orchestrator, body, model_text, record_doc)
    finally:
        chat_orchestrator._ANSWER_LANGUAGE.reset(token)


@pytest.mark.parametrize("language", ("pt", "nb", "nn", "xx"))
def test_localize_reviewed_copy_is_never_called_through_the_full_path(language) -> None:
    """N3 (Fable review 2026-09-24, delta re-review 2026-09-25):
    international_directory_note is rendered directly through cx_render,
    not through utils.directory_fields' own per-field guard, so it needs
    the identical configured-locale check applied explicitly - AND the
    ALIASED locale that check resolves must be what actually gets passed to
    cx_render.render, or nb/nn still reach a live translation call despite
    the guard itself correctly reporting them "configured" (delta finding
    1: chat_orchestrator.py was passing the raw, unaliased language to
    cx_render, whose own locale resolution - app.evidence._locale_key -
    does not know this nb/nn alias).

    Patches ``app.response.cx_render.localize_reviewed_copy`` AND
    ``app.response.cx_render._translate_template`` directly - NOT
    ``services.controlled_copy.localize_reviewed_copy``, which
    ``app.response.cx_render`` imports by NAME at module load time, so
    patching the service module's own attribute never intercepts the call
    ``cx_render`` actually makes (delta finding 2: the original version of
    this test patched the wrong target and passed regardless of whether
    the bug was fixed). Either patched callable raising proves no live-call
    path was reached, for pt/xx (never configured) and nb/nn (aliased to
    the configured "no") alike.

    Before finding 1 was fixed, running this corrected test against the
    unfixed line failed for "nb"/"nn" with the injected AssertionError
    propagating out of ``_translate_template`` - see the diagnostic run
    recorded in the task report. It passes now because the resolved
    locale ("no") is in the 12 configured routes, so ``cx_render.render``
    never reaches ``_translate_template`` at all for nb/nn.
    """
    orchestrator = AIOrchestrator()
    with (
        patch(
            "app.response.cx_render.localize_reviewed_copy",
            side_effect=AssertionError("live translation call attempted: localize_reviewed_copy"),
        ),
        patch(
            "app.response.cx_render._translate_template",
            side_effect=AssertionError("live translation call attempted: _translate_template"),
        ),
    ):
        delivered = _kenya_history_leak_case(orchestrator, language)

    if language in ("nb", "nn"):
        expected_note = cx_render("international_directory_note", "no", country="Kenya/East Africa")
        assert expected_note.startswith("Denne kontaktinformasjonen kommer fra")
        assert expected_note in delivered.answer
        assert delivered.metadata.get("directory_contact_route") is not None
    else:
        assert delivered.metadata.get("directory_contact_route") is None


@pytest.mark.parametrize("language", ("pt", "xx"))
def test_unconfigured_locale_drops_the_whole_block(language) -> None:
    """The fix drops the WHOLE block (never just the note, and never a
    half-English/half-native mix) for a locale with no reviewed
    international_directory_note copy at all."""
    orchestrator = AIOrchestrator()
    delivered = _kenya_history_leak_case(orchestrator, language)

    assert delivered.metadata.get("directory_contact_route") is None
    assert "+254 20 2026869" not in delivered.answer


@pytest.mark.parametrize("language", ("nb", "nn"))
def test_nb_and_nn_locale_still_render_the_block_via_their_no_alias(language) -> None:
    """nb/nn are ALIASED to the configured "no" locale (for both the
    labels and, after this fix, the note too) - they must keep rendering,
    not be treated as unconfigured, and the note must be the reviewed "no"
    copy rather than an English fallback or a half-translated mix."""
    orchestrator = AIOrchestrator()
    delivered = _kenya_history_leak_case(orchestrator, language)

    assert delivered.metadata.get("directory_contact_route") is not None
    assert "+254 20 2026869" in delivered.answer
    expected_note = cx_render("international_directory_note", "no", country="Kenya/East Africa")
    assert expected_note in delivered.answer


# --- CX composition: no contradictory second contact offer -----------------


def _outcome(**overrides):
    base = dict(
        kind=OutcomeKind.EVIDENCE_MISSING, language="en", country="US",
        fields_requested=frozenset({"phone"}), fields_answered=frozenset(), fields_unsupported=frozenset(),
        directory_target=None, clarification_subject=None, failure_layer="output_validator",
        retrieval_availability=None,
    )
    base.update(overrides)
    return ConversationOutcome(**base)


def test_name_missing_fields_is_skipped_for_a_directory_contact_route_response() -> None:
    response = ChatResponse(
        answer=(
            "The approved policy documents currently available do not contain enough information to "
            "answer this question clearly. Please rephrase the question or contact Forever Living "
            "support for an official answer.\n\nThis contact information comes from the international "
            "sponsoring directory for Kenya, not from local policy documents.\n\n- Phone: +254 20 2721133"
        ),
        citations=[], suggestions=[], cards=[], confidence=0.0,
        metadata={"directory_contact_route": {"record_id": "r", "record_country": "Kenya", "labels": ["Phone"]}},
        correlation_id="test",
    )
    new_response, applied = compose_cx_response(
        response, _outcome(), question="What is the Kenya office phone number?", language="en", country="US",
        evidence_documents=(), topic_supported=lambda *_: False,
    )

    assert "evidence_missing_detail" not in applied["cx_applied"]
    assert "do not contain enough information" in new_response.answer
    assert new_response.answer.count("- Phone: +254 20 2721133") == 1


def test_contact_offer_is_suppressed_for_a_directory_contact_route_response() -> None:
    response = ChatResponse(
        answer="Plain fallback text.\n\n- Phone: +254 20 2721133",
        citations=[], suggestions=[], cards=[], confidence=0.0,
        metadata={"directory_contact_route": {"record_id": "r", "record_country": "Kenya", "labels": ["Phone"]}},
        correlation_id="test",
    )
    new_response, applied = compose_cx_response(
        response, _outcome(fields_requested=frozenset()), question="What is the Kenya office phone number?",
        language="en", country="US", evidence_documents=(), topic_supported=lambda *_: False,
    )

    assert "contact_offer" not in applied["cx_applied"]
    assert new_response.answer == response.answer


def test_contact_offer_still_applies_without_directory_contact_route() -> None:
    """Control: an ordinary evidence_missing fallback (no directory-contact-route
    metadata) still gets contact_escalation's offer when the session market has
    a reviewed public contact - proving the suppression above is metadata-gated,
    not a blanket regression."""
    response = ChatResponse(
        answer="The approved policy documents currently available do not contain enough information "
        "to answer this question clearly. Please rephrase the question or contact Forever Living "
        "support for an official answer.",
        citations=[], suggestions=[], cards=[], confidence=0.0, metadata={}, correlation_id="test",
    )
    new_response, applied = compose_cx_response(
        response, _outcome(fields_requested=frozenset()), question="What are your business hours?",
        language="en", country="US", evidence_documents=(), topic_supported=lambda *_: False,
    )

    assert "contact_offer" in applied["cx_applied"]


def test_evidence_missing_detail_key_still_renders_with_no_placeholder_for_every_locale() -> None:
    for language in CX_LOCALES:
        text = cx_render("evidence_missing_detail", language, topic="phone")
        assert text
        assert "{" not in text and "}" not in text


def test_international_directory_note_renders_with_no_placeholder_for_every_locale() -> None:
    for language in CX_LOCALES:
        text = cx_render("international_directory_note", language, country="Kenya/East Africa")
        assert text
        assert "{" not in text and "}" not in text
