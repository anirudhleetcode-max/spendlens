# Category classifier - most confident mistakes (test, logreg, calibrated)

195 wrong of 1245. Abstention threshold 0.3: 90 of these mistakes would still be shown as a suggestion.

| text | true | predicted | conf | kind |
|---|---|---|---|---|
| Sapna Book House | Education | Shopping | 1.00 | merchant_only |
| Sapna Book House | Education | Shopping | 1.00 | merchant_only |
| apna Book House | Education | Shopping | 0.97 | merchant_only |
| SAPNA BOOK HOSE | Education | Shopping | 0.97 | merchant_only |
| Sapna Book House rd sharma | Education | Shopping | 0.97 | merchant_items |
| Reliance Digita | Shopping | Groceries | 0.94 | merchant_only |
| Reliance Digital | Shopping | Groceries | 0.91 | merchant_only |
| Reliance Digital | Shopping | Groceries | 0.91 | merchant_only |
| Delhi Pulic Shool | Education | Transport & Fuel | 0.89 | merchant_only |
| Swiggy Instamart | Groceries | Food & Dining | 0.83 | merchant_only |
| SWIGGY INSTAMART | Groceries | Food & Dining | 0.83 | merchant_only |
| Swiggy Instamart | Groceries | Food & Dining | 0.83 | merchant_only |
| LAKME ALON SERVICE | Other | Transport & Fuel | 0.82 | merchant_items |
| SonyLIV subscription | Entertainment | Education | 0.82 | merchant_items |
| Sapna Book House uniform textbook | Education | Shopping | 0.79 | merchant_items |
| Reliance Digital saree | Shopping | Groceries | 0.71 | merchant_items |
| Delhi Public School | Education | Transport & Fuel | 0.71 | merchant_only |
| Delhi Public School | Education | Transport & Fuel | 0.71 | merchant_only |
| Delhi Public School | Education | Transport & Fuel | 0.71 | merchant_only |
| Reliance Digital power bank | Shopping | Groceries | 0.67 | merchant_items |
| Sapna o0k House textbook 1irary fine | Education | Shopping | 0.64 | merchant_items |
| Kingdom of Dreams subscription | Entertainment | Education | 0.63 | merchant_items |
| Housejoy | Other | Shopping | 0.62 | merchant_only |
| Housejoy | Other | Shopping | 0.62 | merchant_only |
| Housejoy | Other | Shopping | 0.62 | merchant_only |
| HOUSEJOY | Other | Shopping | 0.62 | merchant_only |
| Housejoy | Other | Shopping | 0.62 | merchant_only |
| Housejoy | Other | Shopping | 0.62 | merchant_only |
| Tailor Shop | Other | Shopping | 0.60 | merchant_only |
| Tailor Shop | Other | Shopping | 0.60 | merchant_only |

## Top confusions

| true | predicted | count |
|---|---|---|
| Other | Shopping | 25 |
| Food & Dining | Shopping | 12 |
| Shopping | Groceries | 10 |
| Shopping | Travel | 9 |
| Health | Food & Dining | 9 |
| Education | Shopping | 9 |
| Transport & Fuel | Food & Dining | 7 |
| Entertainment | Shopping | 7 |
