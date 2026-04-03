# SVFE Host2Host Specification — AI Assistant Index

This document is a **navigation and semantics index** for coding against **SmartVista Front End (SVFE) ISO 8583 Host2Host** messages. It does **not** replace the full specification; use it to find the right section quickly, then read detail in the source file.

**Canonical source (workspace):** `docs/SVFE_Host2Host_Specification.md` (Group A version; ISO 8583-2:1993–based external message; ~4700 lines). Same folder as this index.

---

## 1. How to use this index (for AI / developers)

1. **Identify the MTI** (message class) — section 2 below.
2. **Open “Message Formats”** in the source for bit maps and M/C/O per field + MAC inclusion — lines ~1617+.
3. **Resolve Field 3** (processing code: transaction type + account types) — starts ~line 651.
4. **Parse Field 48** almost always: tag **002 = SVFE transaction type** must align with Field 3; structure is Appendix A (~2166+).
5. **Match requests/responses/reversals** using section 5 — wrong matching logic is a common integration bug.
6. For **balances / fees / cashback**, see **Field 54** Appendix B (~4045+).
7. For **installments / ATM counters**, see **Field 61** Appendix C (~4267+).

---

## 2. Transport and framing

| Topic | Detail |
| --- | --- |
| Transport | TCP/IP; single bidirectional session per host pair |
| Roles | Config-dependent: SVFE may be TCP **client or server**; **client must reconnect** if dropped |
| Frame | **2-byte big-endian length** (high byte first) + **raw ISO 8583 message body** |
| Reference | Source `# Host2Host Communication PROTOcol` ~lines 337–348 |

---

## 3. Message types (MTI) — quick map

| MTI | Role |
| --- | --- |
| **1100** | Authorization request |
| **1110** | Authorization response |
| **1120** | Authorization advice (same field layout as 1100; ack **1130**) |
| **1130** | Authorization advice response (same field layout as 1110) |
| **1200** | Financial request (SMS / immediate post; layout aligned with 1100) |
| **1210** | Financial response |
| **1220** | Financial advice (ack **1230**; stand-in / completed at SVFE) |
| **1221** | Financial advice **repeat** (duplicate of 1220 if no 1230) |
| **1230** | Financial advice response |
| **1420** | Reversal advice |
| **1421** | Reversal **repeat** (duplicate of 1420 if no 1430) |
| **1430** | Reversal response |
| **1600** | Administrative / service request (card status, activation, etc.) |
| **1610** | Administrative response |
| **1804** | Network management **request** |
| **1814** | Network management **response** |

**Relationships (high level):**

- 1100↔1110, 1200↔1210, 1420↔1430: request/response pairs.
- 1120→1130, 1220/1221→1230: advice must be acknowledged.
- Repeats (1221, 1421): sent when prior advice ack not received.

Source: `# Host2Host ISO-8583 MESSAGE TYPES` ~350–511; flows under `# Host2Host ISO – 8583 MESSAGE flows` ~513+.

---

## 4. Field 24 (function code) — network & crypto

Used mainly on **1804/1814** and for special auth/financial semantics.

| Code | Meaning | Typical MTI |
| --- | --- | --- |
| **100** | Normal authorization | 1100/1120/1200/1220 |
| **181** | Incremental authorization | 1100/1120/1200/1220 |
| **801** | Sign-on | 1804 |
| **802** | Sign-off | 1804 |
| **811** | Key change (initiator = key creator); Field **53** params, Field **96** key material | 1804 |
| **815** | Key demand (initiator = key receiver) | 1804 |
| **831** | Echo test | 1804 |

**Key exchange (summary):** Master may send **811** with new key data; slave responds **1814**. Slave may send **815** to request key; master responds then sends key change. Issuer vs acquirer key directions are **cross-labeled** across peers (local “issuer key” = remote “acquirer key”). **Timeouts:** Key Demand repeat allowed without limit after **30s**; Key Change repeated by master every **30s**, same key, **abort after 5** failed attempts.

Source: Field 24 table ~949–957; key flow narrative ~551–567.

---

## 5. Message matching (critical for implementations)

### 5.1 Fields that participate in matching (general set)

- Field **2** PAN  
- Field **11** STAN  
- Field **12** local date/time  
- Field **37** RRN  
- **MTI**

Source: `# MESSAGE MATCHING` ~2125–2135.

### 5.2 Match response → original request

- **Keys:** PAN (**2**), STAN (**11**), local date/time (**12**).
- **Special 810:** match on **MTI** + STAN (**11**); request type **800** used as matching MTI value (per spec).
- **Fraud (SVFP):** PAN (**2**) if present; Field **7** transmission time; STAN (**11**).

~2137–2146.

### 5.3 Match reversal → original request

- **Keys:** PAN (**2**), RRN (**37**), local date/time (**12**).
- If **37** absent (spaces): use **11** instead of **37**.

~2148–2152.

### 5.4 Match repeat → original request

- **Keys:** **MTI**, PAN (**2**), STAN (**11**), local date/time (**12**).
- Use appropriate **x00** request MTI for matching value.

~2154–2158.

### 5.5 Cancellation / refund / completion

- **Keys:** **MTI**, PAN (**2**), STAN (**11**), acquirer id (**32**) of original, RRN (**37**) of original — with **non-PAN data carried in Field 90** (Original Data Elements).

~2160–2163.

---

## 6. Data element conventions

- **Presence:** **M** mandatory, **O** optional, **C** conditional (see field description).
- **Variable fields:** length prefix **LL** (2 digits, 01–99), **LLL** (3 digits, 001–999), **LLLL** (4 digits) per field definition.
- **Bitmap:** primary 64 bits; Field **1** secondary bitmap only if fields **65–128** present.
- **MAC:** Message format tables mark **“Field Used For Mac Y/N”** per DE — respect when implementing MAC.

Source: `# Data FieldS` ~582–627; message tables ~1617+.

---

## 7. High-value data elements (where to look in source)

| DE | Name / role | Source anchor |
| --- | --- | --- |
| 1 | Secondary bitmap | ~629 |
| 2 | PAN + matching | ~639 |
| 3 | Processing code (SVFE txn types) | ~651+ |
| 4, 6 | Amounts | ~784+ |
| 7 | Transmission date/time (GMT); **conditional** on several MTIs per revisions | ~806 |
| 11, 12 | STAN, local datetime — **matching** | ~830+ |
| 22 | POS data / card reading context | ~900+ |
| 24 | Function code | ~937 |
| 37, 38, 39 | RRN, auth code, **response code** (large enum) | ~991+ |
| 41–43 | Terminal, merchant id, name/location (**43** has usage variants) | ~1216+ |
| 48 | **Additional data (TLV)** — Usage 1 Host2Host vs Usage 2 Fraud | Appendix A ~2166 |
| 52–53 | PIN data, security control | ~1336+ |
| 54 | **Additional amounts (TLV)** — balances, fees, cashback | Appendix B ~4045 |
| 55 | EMV TLV | ~1377+ |
| 61 | **Counters / installments (TLV)** | Appendix C ~4267 |
| 62 | External fraud system info | ~1436; Appendix F ~4448 |
| 64, 128 | MAC | ~1450, ~1607 |
| 90 | Original data elements (reversals, incremental, cancel/refund/completion) | ~1462 |
| 95 | Replacement amounts (structured) | Appendix D ~4367 |
| 100 | Receiving institution — **two usages** (Host2Host vs fraud) | ~1527 |
| 102–103 | Account identifiers | ~1543 |
| 112 | Payment account data | ~1563; Appendix E ~4413 |
| 123 | Transaction-specific data | Appendix G ~4502 |

---

## 8. Field 48 essentials (Usage 1 — Host2Host)

- **Structure:** `LLL` + repeated `[3-digit tag][3-digit len][data]`.
- **Tag 002:** **SVFE transaction type (n3)** — must be in **all** requests and responses; must be **consistent with Field 3**.
- Many hundreds of optional tags (3DS, tokens, MDES, remittance, SCA, wallet, MIR, etc.) — **always jump from tag number** in Appendix A rather than reading sequentially.

Start: `### Usage 1 – Common Host-to-Host Interface` ~2186.

**Usage 2 (fraud / SVFP):** separate tag semantics from ~3385; do not mix with Usage 1 parsers.

**Private / payment-system tag ranges:** e.g. tags **800–899** payment systems; **900–999** private use — see Appendix A tables.

---

## 9. Issuer-driven installments (behavioral summary)

1. Acquirer signals support: Field **48** tag **125** = `1` on **1100** purchase (when supported).
2. Issuer may offer installment in **1110**: Field **61** tag **013** ∈ {`I`,`B`} with installment detail tags **014** + (**004,007–012** or **005,006,007–008,009,012**, etc. per spec).
3. Acquirer ignores if unsupported or **013** = `F` or absent.
4. If customer opts in, send **1120** with same **37** as original response, **48** tag **013** = **584** (POS Installment Purchase), **61** tag **013** = `I` and selected plan in **61** tags **004** and **007–012**.

Source: `# Data FieldS` issuer installment bullets ~575–580; Field 61 tags ~4301+; Field 48 tags **125**, **124** in Appendix A.

---

## 10. Appendices in source (TLV “sub-specs”)

| Appendix | Topic | ~Line |
| --- | --- | --- |
| A | Field **48** | 2166 |
| B | Field **54** | 4045 |
| C | Field **61** | 4267 |
| D | Field **95** | 4367 |
| E | Field **112** | 4413 |
| F | Field **62** | 4448 |
| G | Field **123** | 4502 |
| — | Revision history | 4546 |

---

## 11. Implementation checklist (quick)

- [ ] Frame read/write: **16-bit length + body**; reconnect policy on client.
- [ ] Bitmap parse for **1–64** and optional **65–128** via DE1.
- [ ] **Field 48 Usage** configured per deployment (Host2Host vs SVFP).
- [ ] **Tag 002** populated and **aligned with Field 3** on every message.
- [ ] **Matching rules** implemented per section 5 (especially **37** vs **11** fallback for reversals).
- [ ] **Advice ack**: 1120→1130, 1220/1221→1230, handle **repeats**.
- [ ] **1804/1814**: echo **831**, sign-on/off **801/802**, key **811/815** with **53/96** and timeout behavior.
- [ ] **MAC fields** 64/128 only if scheme uses them; follow per-MTI “Field Used For Mac” columns.
- [ ] Large enumerations (**Field 39** response codes, full **Field 3** matrix): use source text search by code value.

---

## 12. Document section index (source line numbers)

| Section | ~Start line |
| --- | ---: |
| Overview | 329 |
| Communication protocol | 337 |
| Message types | 350 |
| Message flows | 513 |
| Data fields (attributes, formats, DE descriptions) | 582 |
| Message format tables | 1617 |
| Message matching | 2125 |
| Appendix A–G + revisions | 2166–4724 |

---

*End of index. For authoritative wording, tables, and diagrams, always consult `SVFE_Host2Host_Specification.md` (in this directory) at the line ranges above.*
