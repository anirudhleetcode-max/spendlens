# Worst parse failures - ocr_configs_sroie_dev / production

Generated 2026-11-26 16:33. 70 field errors (merchant: 40, total: 21, date: 9). Sorted by confidence, highest first.

| image id | field | expected | got | conf | source | OCR snippet |
|---|---|---|---|---|---|---|
| X51005719917 | merchant | DOMMAL FOOD SERVICES SDN BHD | Domino's Pizza | 0.97 | lexicon | ; TAX INVOICE \| DOMINO'S PIZZA \| GST REF NO : 001694261248 |
| X51006647932 | total | 87.10 | 87.08 | 0.91 | keyword:grand total | GST : 4.93 \| Grand Total : 87.08 \| Rounding Adjustment: |
| X51007846393 | date | 20/06/2018 | 2018-08-20 | 0.87 | labelled | Invoice No: S$P-nul1-18/06/20-1022050 \| Date + 20/08/2018 18:07:10 \| Payment Type: Cash |
| X51007339650 | date | 13/12/2017 | 2017-12-18 | 0.85 | labelled | CASH \| RECEIPT 4: CSPO420207 DATE: 18/12/2017 \| SALESPERSON : AHOI9 TINE: 17:53:00 |
| X51007846270 | total | RM21.85 | 85.0 | 0.77 | keyword:grand total | Rounding RMO.02 \| Grand totalRM21 2 85 ; \| Total Paid RH50.00 |
| X51007339657 | date | 25/12/2017 | 2017-12-26 | 0.76 | labelled | CASH \| RECEIPT #: CSPO422102 DATE: 26/12/2017 \| SALESPERSON : AHO19 TINE: 1534400 |
| X51006913051 | total | 31.00 | 31.88 | 0.70 | fallback:largest amount+digit-repair | Totai Items: 4 \| Sub Total: “31.00 \| Less Discount: 0.00 |
| X51005724621 | total | 127.20 | 7.2 | 0.69 | keyword:total | SR 6 120.00 7.20 \| Total: 120.00 7.20 \| \| GOODS SOLD ARE NOT RETURNABLE, THANK YOU. |
| X51007846393 | total | RM14.20 | 20.0 | 0.68 | keyword:grand total | Rounding RMO.02 \| grand TotalM14 20 \| Total Paid RM20.20 |
| X51005719902 | total | 25.15 | 1.42 | 0.66 | keyword:total | So mt cate So ove ate ek ow ow ee ote eae avo ' \| (Total Included GST @ 4%: 1.42) \| GOOUS SOLD NOT RETURNAPBLE/EXCHANGEABLE! |
| X51008164996 | date | 17-06-2018 | 2018-06-01 | 0.66 | unlabelled | TOTAL: 58.00 \| Closed: 1 -06-2018 14:19:35 \| \| Server: 113 CASHIL |
| X51005745214 | total | 45.35 | 45.54 | 0.65 | keyword:total | 270 CSR GULA 12%1K6* RH3S.20 z \| Total Sales (Inclusive GST) RM 45.54 \| Rounding Adjustment RM 01 |
| X51008142005 | total | 65.70 | 65.72 | 0.65 | keyword:total | GST Payable: 3.12 \| \| Total (Inclusive of GST): 65.72 \| \| Rounding Adj ~0.02 |
| X51007846309 | total | RM6.00 | 7.0 | 0.64 | keyword:total | GST @0%: RM0.00 \| Nett Total: RM6.00 7 \| Payment Mode Amount |
| X51005741944 | total | 41.95 | 47.98 | 0.62 | keyword:total | infiniti 97 E4423 2.570 16.32 41.95 $ \| TOTAL SALES RH 47.98 \| TOTAL AMOUNT PAYABLE |
| X51006392313 | total | RM28.05 | 5.0 | 0.62 | keyword:total | Rounding Adjustment RMO.02 \| het Total rH28 05 \| Fayiment Metnod CASH |
| X51005361898 | total | 55.10 | 3.12 | 0.60 | keyword:total | SR 6.00 52.00 3.12 \| TOTAL: 52.00 3.12 \| Note. (*) Indicated The Item Sold Has Been Related |
| X51005719917 | total | 60.60 | 33.0 | 0.60 | keyword:grand total | Coupon Discount : 27.60 \| Grand Total : 33.00 \| Payment ; 50.00 |
| X51006466056 | total | 11.25 | 3.0 | 0.60 | keyword:total | Item Court 3 \| Item Total 3 \| GST Summary Amount GST |
| X51005719882 | merchant | 99 SPEED MART S/B | Taman Berkeley | 0.51 | header | LOT P.T. 2811, JALAN ANGSA, \| TAMAN BERKELEY \| 41150 KLANG, SELANGOR |
| X51007846270 | merchant | MOONLIGHT CAKE HOUSE SDN BHD | No.1 Jalan Permas 105 Bandar Baru Permas Jaya | 0.51 | header | (GST Reg No: 001559298048) . \| No.1, Jalan Permas 10/5, Bandar Baru Permas Jaya \| 81750 Johor Bahru, Johor. Tel No.: 07-387 3322 |
| X51005568911 | merchant | MR. D.I.Y. (KUCHAI) SDN BHD | Kawasan Perindustrian Balakong | 0.50 | header | LOT 1851-A & 1851-B, JALAN KPB 6, \| KAWASAN PERINDUSTRIAN BALAKONG, \| 43300 SERI KEMBANGAN, SELANGOR |
| X51006619496 | merchant | 99 SPEED MART S/B | Taman Berkeley | 0.50 | header | LOT P.T. 2811, JALAN ANGSA, \| TAMAN BERKELEY \| 41150 KLANG, SELANGOR |
| X51008114217 | merchant | MR. D.I.Y. (KUCHAI) SDN BHD | Kawasan Perindustrian Balakong | 0.50 | header | LOT 1851-A & 1851-B, JALAN KPB 6, \| KAWASAN PERINDUSTRIAN BALAKONG, \| 43300 SERI KEMBANGAN, SELANGOR |
| X51005605285 | merchant | AEON CO. (M) BHD. | Jln Jejaka Taman Maluri | 0.49 | header | 3 FLOOR, AEON TAMAN MALURI SC \| JLN JEJAKA, TAMAN MALURI \| CHERAS, 55100 KUALA LUMPUR |
| X51005719902 | merchant | KING'S CONFECTIONERY S/B | No.41 Jalan Seri Bintang 2 | 0.49 | header | KING’S CONFECTIONERY S/B 273500-U (KSB) \| NO.41, JALAN SERI BINTANG 2 \| TAMAN SRI BINTANG, |
| X51006619698 | merchant | MR. D.I.Y. (M) SDN BHD | Kawasan Perindustrian Balakong | 0.49 | header | LOT 1851-A & 1851-B, JALAN KPB 4, \| KAWASAN PERINDUSTRIAN BALAKONG, \| 43300 SERI KEMBANGAN, SELANGOR |
| X51007339657 | merchant | AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD | Aik Huat Hakdware | 0.45 | header | S \| AIK HUAT HAKDWARE \| ENTERPRISE (SETIA |
| X51007846286 | merchant | UNIHAKKA INTERNATIONAL SDN BHD | Pcl Xl Error . | 0.43 | header | PCL XL error . \| Warning: ILlegalMediaSource |
| X51007339650 | merchant | AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD | Alk Huat Hardware | 0.37 | header | ALK HUAT HARDWARE \| ENTERPRISE (SETIA |
| X51006332649 | total | 217.00 | 247.06 | 0.35 | fallback:largest amount | Tot! Inclusive GST: 217.00 \| TOE 247.06 \| GST Summary: Amauat Tay |
| X51006387951 | total | RM3.00 | 6.0 | 0.35 | fallback:largest amount | Parking Fee , Fite. &3 \| GSTCInctuaaxd) 6.00 % FED. WV \| Total D1 [M3.00 |
| X51006555125 | merchant | KHIAM AIK CHAN SDN BHD | 7500 Subang Jaya Selanger D.e. | 0.35 | header | No. 76, Jalan SS15/4B, \| #7500 Subang Jaya, Selanger D.E. \| GST Reg.: 000555819008 |
| X51007339657 | total | 2.50 | 9.14 | 0.35 | fallback:largest amount | COLE AMOUNT =% — TAX/AMT \| SR omy % g.14 \| TAX TOTAL: 0.15 |
| X51007339653 | merchant | AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD | Atk Huat Harduake | 0.33 | header | ATK HUAT HARDUAKE \| ENTERPRISE (SETIA |
| X51007103578 | merchant | MR. D.I.Y. (M) SDN BHD | 2 Boy Of | 0.31 | header | 2 Boy of \| “ks |
| X51006913051 | merchant | THE TOAST F&B SDN BHD | Oy On Sle | 0.24 | header | Oy on SLE \| ee \| |
| X51008164997 | merchant | ONE ONE THREE SEAFOOD RESTAURANT SDN BHD | Lll Eee Lee Lll Lll | 0.24 | header | <= lll eee lee lll lll \| ke |
| X51005719893 | merchant | MR . DAKGALBI SOLARIS | He Dako Solaris | 0.22 | header | He Dako Solaris \| BRN GST No. 000417619968 President: Kang |
| X51005361950 | merchant | 99 SPEED MART S/B | Len | 0.21 | header | } \| len, \| o9 SPEED Nant SIR Eig \| |
