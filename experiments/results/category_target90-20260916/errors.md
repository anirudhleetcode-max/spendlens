# Category classifier - most confident mistakes (test, complement_nb, calibrated)

521 wrong of 1245. Abstention threshold 0.95: 5 of these mistakes would still be shown as a suggestion.

| text | true | predicted | conf | kind |
|---|---|---|---|---|
| Sapna Book House | Education | Shopping | 1.00 | merchant_only |
| Sapna Book House | Education | Shopping | 1.00 | merchant_only |
| Sapna Bok House | Education | Shopping | 0.98 | merchant_only |
| SAPNA BOOK HOUSE COACHING FEE NERT COURSE ENROLMCNT | Education | Shopping | 0.95 | merchant_items |
| SapnBook House | Education | Shopping | 0.95 | merchant_only |
| Sapna Book House ncert course enrolment coaching fee | Education | Shopping | 0.94 | merchant_items |
| Sapna Book House reference book course enrolment coaching fee ncert | Education | Shopping | 0.92 | merchant_items |
| Amazon Prime | Entertainment | Shopping | 0.92 | merchant_only |
| Amazon Prime | Entertainment | Shopping | 0.92 | merchant_only |
| Amazon Prime | Entertainment | Shopping | 0.92 | merchant_only |
| Sapna Book House ncert coaching fee reference book course enrolment a4 | Education | Shopping | 0.92 | merchant_items |
| Amazon Prime water park | Entertainment | Shopping | 0.86 | merchant_items |
| Amazon Prime game purchase | Entertainment | Shopping | 0.86 | merchant_items |
| Amazon Prime game purchase | Entertainment | Shopping | 0.86 | merchant_items |
| DELHI JL BOORD | Bills & Utilities | Transport & Fuel | 0.84 | merchant_only |
| Max ashin | Shopping | Health | 0.83 | merchant_only |
| Amazon Prime row f water park | Entertainment | Shopping | 0.83 | merchant_items |
| AMAZON PRIME ROW F GAME PRCHASE | Entertainment | Shopping | 0.83 | merchant_items |
| Sapna hook House reference book coaching fee ncert exam fee a4 sheets | Education | Shopping | 0.82 | merchant_items |
| Sapna Boo Hose | Education | Shopping | 0.82 | merchant_only |
| Delhi Jal Board | Bills & Utilities | Transport & Fuel | 0.81 | merchant_only |
| DELHI JAL BOARD | Bills & Utilities | Transport & Fuel | 0.81 | merchant_only |
| Delhi Jal Board due date | Bills & Utilities | Transport & Fuel | 0.77 | merchant_items |
| SWIGGY INSTAMART SUGAR AML BUTTER POATO LAY5 CHIPS AASHIRVAAD ATTA | Groceries | Food & Dining | 0.76 | merchant_items |
| Udupi Grand tandoori roti jeera rice | Food & Dining | Groceries | 0.76 | merchant_items |
| Blue Dart | Other | Food & Dining | 0.76 | merchant_only |
| Blue Dart | Other | Food & Dining | 0.76 | merchant_only |
| Blue Dart | Other | Food & Dining | 0.76 | merchant_only |
| Sapna Book House exam fee coaching fee reference book a4 sheets ncert  | Education | Shopping | 0.76 | merchant_items |
| Sapna Book House coaching fee course enrolment exam fee ncert referenc | Education | Shopping | 0.76 | merchant_items |

## Top confusions

| true | predicted | count |
|---|---|---|
| Entertainment | Bills & Utilities | 35 |
| Entertainment | Groceries | 34 |
| Education | Shopping | 27 |
| Food & Dining | Groceries | 25 |
| Shopping | Travel | 24 |
| Shopping | Health | 23 |
| Shopping | Groceries | 20 |
| Groceries | Food & Dining | 18 |
