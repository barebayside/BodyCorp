# Queensland body corporate committee rules (for software)

Scheme: Alatai on the Park, Brisbane, 48 lots, residential community titles scheme.

**Status: DRAFT. This is guidance, not legal advice.** It stays Draft until it has been checked against Alatai's CMS and by-laws. Researched 10 Nov 2026 from primary sources only.

## Sources and versions

| Short name | Instrument | Version used | URL |
|---|---|---|---|
| **Act** | Body Corporate and Community Management Act 1997 (Qld) | Current reprint, in force from 1 August 2025 (shown as current on 10 Nov 2026) | https://www.legislation.qld.gov.au/view/whole/html/inforce/current/act-1997-028 |
| **SM** | Body Corporate and Community Management (Standard Module) Regulation 2020, SL 2020 No. 233 | Current reprint, in force from 1 August 2025 (includes the 2024 SL No. 40 animal and motion changes) | https://www.legislation.qld.gov.au/view/whole/html/inforce/current/sl-2020-0233 |
| **AM** | Body Corporate and Community Management (Accommodation Module) Regulation 2020, SL 2020 No. 229 | Current, from 1 August 2025 | https://www.legislation.qld.gov.au/view/whole/html/inforce/current/sl-2020-0229 |
| **SSM** | Body Corporate and Community Management (Small Schemes Module) Regulation 2020, SL 2020 No. 231 | Current, from 1 August 2025 | https://www.legislation.qld.gov.au/view/whole/html/inforce/current/sl-2020-0231 |
| **AIA** | Acts Interpretation Act 1954, s 38 (counting time) | Current, from 1 February 2024 | https://www.legislation.qld.gov.au/view/whole/html/inforce/current/act-1954-003 |
| **BCCM-Office** | Office of the Commissioner for Body Corporate and Community Management, qld.gov.au guidance (dates show each page's "last updated") | Read 10 Nov 2026 | https://www.qld.gov.au/housing/body-corporate |

How the citations work:
- "SM s 55(2)" means section 55, subsection (2) of the Standard Module.
- "Act s 205" means the BCCM Act.
- Office pages are for practical interpretation only. Where an Office page and the legislation differ, the legislation governs.
- **UNCONFIRMED** means I could not confirm the point from the primary source text. Treat it as a design assumption, not law.

---

## 1. Which regulation module applies, and how to tell

### Rule
- Each scheme has exactly one regulation module (Act s 21(5)).
- A module applies if the **community management statement (CMS) names it** (Act s 21(2)).
- A named module does **not** apply if the module sets conditions the scheme doesn't meet (Act s 21(3)). In that case the Standard Module applies by default (Act s 21(4); SM s 3(2)).
- If the CMS names no module, the Standard Module applies (Act s 21(4)(b)(i); SM s 3(2)).

### Can each module apply to Alatai (48 lots)?

| Module | Condition to apply | Possible for Alatai? | Citation |
|---|---|---|---|
| Standard | Default when no other module applies | **Yes**, and the most likely | SM s 3 |
| Accommodation | Lots are predominantly "accommodation lots", or were intended to be when the CMS first named it. An accommodation lot is one leased or let (or available to lease) for **long- or short-term residential** accommodation, or part of a hotel | **Yes, possibly.** A residential building where most lots are rented out (for example, with an onsite letting agent) can validly be under this module | AM s 3(2), (3) |
| Commercial | Lots are predominantly commercial lots | Unlikely | Commercial Module s 3 |
| Small Schemes | Basic scheme, no letting agent, **6 lots or fewer** | **No.** 48 lots is over the limit | SSM s 3(2)(c) |
| Specified Two-lot | Two-lot schemes only | No | (BCCM-Office "Committee's role") |

### How the software should find out (do not assume)
1. Read the scheme's **current CMS**, recorded with Titles Queensland. It states the regulation module.
   - BCCM-Office says to contact Titles Queensland to find out which Act and regulation apply ("Committee's role", updated 16 Nov 2023).
2. Cross-check with any **body corporate certificate** (BCCM Form 33). It must state the regulation module that applies (SM s 233AA(1)(b)(ii)).
3. Store the module as a scheme setting (`regulation_module`), with the CMS dealing number and date as evidence. Block the committee rules engine until this is set.

### Why it matters
- The Accommodation Module's committee rules are **mostly the same in substance** as the Standard Module's, but the **section numbers differ**. Each AM section is labelled with its SM twin, for example "[SM, s 55]".
- I compared notice of meetings, quorum, voting outside a meeting, owner motions, spending limits and maximum committee size. They match.
- **Known difference:** the AM has **no "notice of opposition"** process (SM s 72–73). BCCM-Office says this process is "Standard Module only" ("Committee voting", updated 30 Apr 2024). I searched the AM text and found no such provision.
- **UNCONFIRMED:** a full clause-by-clause comparison of AM and SM was not done. If Alatai turns out to be under the AM, re-map every citation below to its AM equivalent.

**Everything below assumes the Standard Module.**

---

## 2. Committee make-up

### Must there be a committee?
- Yes. There must be a committee (SM s 7(1); Act s 98).
- **Exception:** there is no committee if a body corporate manager is engaged under SM ch 3 pt 5 to do the committee's job (SM s 7(2), s 74). See "Body corporate manager" below.

### Positions

| Item | Rule | Citation |
|---|---|---|
| Executive positions | Chairperson, secretary and treasurer **must** exist, even if a body corporate manager is authorised to use executive powers | SM s 9(2) |
| One person, several roles | One person may hold **all three** executive positions, or any two | SM s 9(3); BCCM-Office "Committee's role" confirms "all or any 2" |
| Votes when holding several roles | Still **only 1 vote** | SM s 65(5) |
| Minimum size | At least **3 voting members** (not counting a "minor committee") | SM s 9(4) |
| Maximum size | **7 voting members** for a scheme with 7 or more lots. A principal scheme in a layered arrangement may set up to 12 by ordinary resolution | SM s 9(4); SM sch 1 "maximum number" |
| Ordinary members | The remaining seats up to the maximum, after the executive positions are filled | SM s 9(1)(b), s 36–39 |
| Non-voting members | A **body corporate manager** and a **caretaking service contractor** are automatically committee members, without election. They **cannot vote** and do not count towards quorum | SM s 12; SM s 60(3) |
| Minor committee | Only applies when there are 3 or fewer distinct owners. Not relevant to 48 lots | SM s 13(3)–(8) |

### Who can be a voting member (SM s 10)
A person must be an individual who is nominated by a member of the body corporate, and who is one of the following:
- a member of the body corporate (a lot owner);
- for an individual owner: a family member of the owner, or the owner's attorney under a power of attorney;
  - "family" means spouse, adult children (including step-children and adopted children), parents (including step-parents), and brothers or sisters (SM sch 1);
- for a corporate owner: a director, secretary or other nominee of the company;
- for a subsidiary scheme: its representative.

**Ineligible**, even if otherwise eligible (SM s 10(2)):
- a body corporate manager, service contractor or letting agent;
- an associate of any of those (except an owner who is an associate only because the letting agent lets their lot);
- anyone running a letting business for the scheme who is not the authorised letting agent;
- an owner who **owes a body corporate debt** at the time the committee is chosen;
- a person nominated by such a debtor.

**One seat per lot:**
- Only 1 co-owner of a lot can be a voting member on the basis of that lot (SM s 11(1)).
- Only one of these can sit on the basis of the same lot: the owner, a family member, or an attorney (SM s 11(2)).
- Exception: a second co-owner may be appointed to bring the committee up to 3 members (SM s 38(3), s 42(2), s 50(8)).

### How the committee is chosen
- It is elected at **every AGM** (SM s 13(1)).
- The election is by **ballot**, which is **secret** unless the body corporate decides by ordinary resolution to use an open ballot (SM s 15(2), (3)).
- Each lot has an equal vote in committee elections (SM s 15(4)).
- **Nominations** (SM s 16):
  - The **secretary** must send every owner on the roll a notice inviting nominations.
  - The notice must also say that a debtor owner, and anyone that owner nominates, can't be elected.
  - It must be sent **at least 3 weeks, and no earlier than 6 weeks, before the end of the financial year**.
  - Nominations close at the **end of the financial year**.
  - The secretary acknowledges each nomination in writing "as soon as practicable".
- **Nomination rights:**
  - An owner may nominate 1 person.
  - An owner of 2 lots may nominate 2 people.
  - An owner of more than 2 lots may nominate 3 people (because the scheme has 7 or more lots).
  - A debtor's nomination is invalid (SM s 17).
- **Nomination content:** name, positions sought, whether the candidate is an owner, and, if not, their address, category and nominating owner. It must also give details of any **payment** the candidate will seek (SM s 18).
- **Ballot order:** chairperson, then secretary, then treasurer, then ordinary members (SM s 32).
- **Ballots are the last business** of the AGM (SM s 31(1)).
- **New committee takes office** immediately after the AGM closes (SM s 31(2)).
- **Unopposed:** the chair of the meeting declares the person elected (SM s 35(1)).
- **No nomination for an executive position:** the chair invites nominations from the floor, and accepts written nominations from absent members (SM s 35(2)).
- **Ties:** decided by chance, in a way the meeting chooses (SM s 35(7), s 39(3)).
- **Electronic voting** in committee elections is allowed only if:
  - the body corporate approves it by ordinary resolution; and
  - the system meets the conditions in SM s 24 (for a secret ballot: it hides the voter's identity, rejects ineligible or double votes, and only the secretary receives the votes) (SM s 24, s 29).

### If an AGM leaves gaps
This applies if an executive position is unfilled, or fewer than 3 voting members are elected (SM s 40–43):
- The elected members must **call an EGM within 1 month** after the AGM (SM s 41(1)).
- The EGM must be **held within 2 months** after the AGM (SM s 41(2)).
- At the EGM, people can be appointed **without an election** (SM s 42).
- The agenda **must** include a motion to engage a body corporate manager under ch 3 pt 5. It is considered last, and only if the gaps remain after appointments (SM s 43).

### Term and vacancies
- **Term:** a member holds office until a replacement is chosen, normally at the next AGM (SM s 44(1)).
- **A position becomes vacant automatically** if the member (SM s 44(2), (3)):
  - dies;
  - becomes ineligible (for example, sells their lot, their nominating owner sells, or they become a contractor, manager or letting agent);
  - **resigns in writing** to the chairperson or secretary;
  - **misses 2 consecutive committee meetings** without the committee's leave (attending by proxy or authorised electronic means counts as present);
  - is convicted of an indictable offence;
  - is removed by **ordinary resolution** of the body corporate;
  - is removed for breaching the **code of conduct** (SM s 45).
- **Filling a casual vacancy** (SM s 46–51):
  - Within **1 month** of the vacancy, the committee must take one of these steps:
    - if the remaining members still form a quorum: **appoint** an eligible person, **or** call a general meeting to elect someone;
    - if the remaining members are below quorum: **call a general meeting** to elect someone (SM s 48).
  - The general meeting notice must include an explanatory note covering (SM s 49):
    - who can nominate (owners who are not debtors);
    - how to nominate (orally at the meeting, or in writing to a named committee member);
    - that owners must be **present in person** to vote.
  - A vacancy caused by the body corporate removing a member may be filled at that same general meeting, without an election (SM s 47).
  - At a vacancy general meeting, the agenda **must** include a motion to engage a body corporate manager under ch 3 pt 5 (SM s 51).
- **Removal for breaching the code of conduct** (SM s 45; Act s 101B):
  1. The body corporate decides by ordinary resolution to give the member a written notice. The notice states the breach in 600 words or fewer.
  2. The member has at least **21 days** to reply to other owners, in 600 words or fewer. If the member asks, the body corporate pays the postage and copying costs.
  3. A removal motion goes on the **next general meeting** after that period, with the notice attached.
  4. The member is removed if the motion passes by ordinary resolution.

### Body corporate manager (BCM) doing secretary or treasurer work
There are two different arrangements:

**A. Authorisation (committee still exists)** (Act s 119):
- The body corporate may authorise a BCM **in writing** to use some or all of an **executive member's** powers.
- The body corporate **must not stop the executive member** from using that power themselves, or from directing the BCM how to use it (Act s 119(3)).
- The authorisation can be revoked in writing at any time (Act s 119(4)).
- The BCM is a **non-voting** committee member (SM s 12).
- Giving a document to a BCM who holds the secretary's powers counts as giving it to the secretary (SM s 222).
- Register of engagements: it must record which executive powers the BCM is authorised to use (SM s 227(2)(d)).
- If the BCM runs the funds:
  - the BCM must follow the fund rules (SM s 168);
  - the BCM prepares the monthly reconciliations (SM s 170(1)(a), (3)(a));
  - the BCM must hand over the financial records within **30 days** after the authorisation ends (SM s 168(4)).
- A BCM decision that conflicts with a committee decision is **void** (Act s 100(3)).

**B. Chapter 3 Part 5 engagement (no committee at all)** (SM s 74–78):
- This is only possible at an AGM, EGM or vacancy meeting where an executive position is still unfilled or fewer than 3 voting members were found.
- It needs a **special resolution**, with **no proxy votes**, and is decided by secret ballot unless the meeting decides by ordinary resolution on an open ballot.
- The engagement ends at the next AGM, or after 12 months, whichever comes first.
- The BCM must report to every owner within 21 days after each quarter.
- **Software implication:** if the scheme setting is "ch 3 pt 5 engagement", switch off committee features. The BCM fills every role (SM s 5(2)).

---

## 3. Duties and powers of each executive position

Important points before the table:
- **Most "duties" belong to the body corporate or the committee as a whole, not to a position.** The legislation gives the secretary many process tasks. It gives the chairperson meeting-chairing tasks. It gives the **treasurer almost nothing**.
- BCCM-Office says:
  - "The treasurer's duties under the legislation are limited."
  - A treasurer "may prepare budgets, manage funds and prepare levy notices, although the legislation does not require them to."
  - "The secretary often takes minutes of meetings, although the legislation does not require them to."
  - "The chairperson does not have more authority than anyone else on the committee." ("Committee's role", updated 16 Nov 2023)
- **The committee's job overall** (Act s 100–101):
  - its decisions are body corporate decisions, except on restricted issues;
  - it must put lawful body corporate decisions into effect;
  - it **must act reasonably**.
- **No delegation:** the body corporate cannot delegate its powers (Act s 97). The only route for handing over powers is a BCM authorisation under Act s 119–120.

| Position | Must do | May do | Must not do | Citation |
|---|---|---|---|---|
| **Chairperson** | Chair every committee meeting they attend (in person or electronically). Chair every general meeting they attend. Call a committee meeting when a quorum asks in writing **and the secretary is absent**; it must be held within 21 days. At AGM elections: check each vote is valid, count and record it, declare results with vote numbers, declare unopposed candidates, and invite floor nominations for empty positions. At general meetings: declare each motion's result (for, against, abstentions) and **rule out of order** a motion that conflicts with the Act, regulation or by-laws, or is unlawful (with reasons, recorded in the minutes). Receive written resignations. Receive animal requests and EGM requests when the secretary is absent | Call a committee meeting in the secretary's absence. Hand vote scrutiny to an independent attendee who is not a candidate | Cast more than 1 vote. **There is no casting vote**: a tied committee vote is lost. Act outside committee decisions (the chair has no extra authority) | SM s 54(1)(a), (2), (3); s 59(1); s 97(1); s 33–35, 37–39; s 114; s 98; s 44(2)(c); s 58A(2); s 82A(2); s 84(1)(b); s 65(4), (5); BCCM-Office "Committee voting" (tie lost) and "Committee's role" |
| **Secretary** | **Meetings:** call committee meetings. Call one when a quorum asks in writing; it must be held within 21 days. Give committee members 7 days' notice (2 days if all voting members agree), with an agenda. Send the advice and agenda to owners and the noticeboard at the same time. **Voting outside a meeting:** give the written notice to all committee members and the advice to owners at the same time (or another member authorised by a majority of voting members may do it). **Minutes and records:** give minutes and the "record of motions" to every committee member and every owner (except those who have opted out) **within 21 days**. **Receiving:** owner motions, animal requests, committee proxy forms, owners' 24-hour attendance notices, notices of opposition, the 15 km meeting-place objection, EGM requests (must call the EGM within **14 days**), and resignations. Keep a list of owners who have opted out of committee notices or minutes. **AGM:** send the nomination notice 3 to 6 weeks before the financial year ends, inviting motions as well. Acknowledge nominations. Prepare ballot papers and voting papers and send them with the AGM notice. Keep custody of all votes. Hand ballots to the chair. Have the roll, voter list, proxies and votes available at general meetings. Give records to a non-secretary who has called a general meeting. The secretary's name and contact address must appear in the minutes | Appoint a committee proxy, **only with the committee's approval**. Be the person who receives electronic election votes | Appoint a proxy without committee approval. Let anyone else receive electronic committee-election votes | SM s 54–55; s 57; s 68(4); s 71(2)–(5); s 58(2); s 58A(2); s 121(4); s 63(2); s 72(3); s 56(3); s 84(3); s 44(2)(c); s 16; s 86(8); s 22, 27; s 25(3), 30(3); s 31(5); s 88; s 113; s 118(3); s 71(6)(j); s 117(3)(i); s 122(2)(a); s 24(2)(c) |
| **Treasurer** | Prepare a **monthly reconciliation statement** for each administrative and sinking fund account **within 21 days after month end**. This applies **only if** the body corporate has decided this by ordinary resolution **and** no BCM administers the fund (if a BCM does, the BCM prepares them) | Appoint a committee proxy, **only with the committee's approval**. In practice: budgets, levy notices and fund management, **not required by law** (BCCM-Office) | Appoint a proxy without committee approval | SM s 170(1)(b), (2), (3)(b); s 122(2)(a); BCCM-Office "Committee's role" |
| **Ordinary member** (and every voting member, including executives) | Follow the **code of conduct**: understand the Act, act honestly and fairly, keep information confidential, act in the body corporate's best interests, cause no nuisance, and **disclose conflicts**. Declare any direct or indirect interest at the meeting before an issue is considered | Attend in person, by proxy (up to 2 meetings a year) or by authorised electronic means. Call a meeting if the secretary and chair are absent and a quorum agrees | Vote while a **debtor** (but still counts towards quorum). Vote on a matter where they have a **conflict**. Receive a benefit from a caretaking or service contractor unless it is allowed or authorised by ordinary resolution. Be paid unless authorised (see section 6) | Act s 101B, sch 1A; SM s 66; s 61; s 125(2); s 54(1)(b); s 64; s 79; s 52(1)(f), 53 |
| **Committee (collectively)** | Prepare the **proposed budgets** for each AGM after the first. Ensure **full and accurate minutes** and a **record of motions** are kept. Decide owner motions within **6 weeks**. Decide animal requests within **21 days**. Fill vacancies within **1 month**. Prepare the agenda and explanatory notes for every general meeting. Obtain 2 quotes for major spending | Fix an **interim levy** before the AGM, based on the previous year's levels. Authorise a member to call a general meeting. Authorise electronic attendance at committee meetings | Decide restricted issues. Spend over its limit. Act on resolutions inside the opposition window | SM s 160(5); s 71(1); s 58; s 58A–58B; s 48; s 93; s 173–174; s 162(3); s 82(1); s 61(2); s 52; s 172; s 73 |

Body corporate (not a position) duties that the software should still assign to someone:
- Levy notices at least **30 days** before each due date (SM s 163).
- Keep accounts (SM s 175).
- Audit (SM s 176).
- Roll updates within **14 days** (SM s 225).
- Start debt recovery within **2 months** after a levy has been unpaid for 2 years (SM s 166(2)).
- **UNCONFIRMED (practice choice, not law):** assign these to the treasurer or BCM by default.

---

## 4. Committee meetings

### Calling and notice
- **Who calls:** the secretary; the chairperson if the secretary is absent; or any member, with a quorum's agreement, if both are absent (SM s 54(1)).
- **Request by a quorum:** the secretary (or the chair, if the secretary is absent) **must** call the meeting. It must be **held within 21 days** of the request. If it isn't, any member with a quorum's agreement may call it (SM s 54(2)–(4)).
  - The secretary and chair are presumed absent if a request sent to the body corporate's address for service gets no reply within **7 days** (SM s 54(5)).
- **Notice to committee members:** written. It goes to **all other members, including non-voting members**, and states when and where (SM s 55(1); BCCM-Office "Calling a committee meeting").
- **Notice period:** at least **7 days**. This can be cut to at least **2 days** only if **all voting members** either voted for it at the previous meeting or agreed in writing (SM s 55(2)).
  - "At least 7 days" means 7 **clear** days: exclude both the day the notice is given and the meeting day (AIA s 38(1)(a)).
- **Advice to owners:** at the **same time** as notice goes to members (SM s 55(3), (4)):
  - put on the **noticeboard**, if there is one;
  - **give to each owner individually**, unless the owner has told the secretary they don't want it and hasn't withdrawn that;
  - include **when, where and the agenda**.
- **Agenda contents** (SM s 57):
  - the substance of each issue;
  - a motion to **confirm the last meeting's minutes**;
  - a motion to **confirm every resolution passed outside a meeting** since the last meeting.
  - Other issues raised at the meeting may also be considered (SM s 57(2)).
- **Place:** the committee decides. It must be **within 15 km of scheme land** if members making up at least half a quorum ask in writing to the secretary (SM s 56).
- **How often:** there is no minimum or maximum number of meetings (BCCM-Office "Running a committee meeting").

### Attendance
- **Voting members** can attend (SM s 61):
  - in person;
  - by proxy;
  - by **electronic means authorised by committee resolution** (for example, email, teleconference or video). The resolution can cover one meeting or all meetings, and one method or any method.
- **Non-voting members** (BCM, caretaker) can attend in person or electronically. The committee can exclude them from items about (SM s 62):
  - a dispute between the body corporate and them, or with an owner or occupier;
  - their own engagement or letting authorisation.
- **Owners and their representatives** (SM s 63):
  - They must give the secretary **written notice at least 24 hours before** the meeting.
  - A representative's notice must also include their address, category, the owner's name, and evidence of authority (unless already on the roll).
  - They may observe, and speak **only if invited**. The committee may direct them to leave if they don't comply.
  - The committee can exclude them from items about:
    - by-law breaches;
    - starting a proceeding that isn't a restricted issue;
    - proceedings against the body corporate;
    - disputes with an owner or occupier, the BCM or the caretaker.
- **Others** may attend only if invited by a majority of the voting members present (SM s 63(1)(b)).

### Quorum
- At least **half the voting members** (SM s 60(1)), so quorum = ceiling(voting members ÷ 2):
  - 3 members → 2
  - 4 → 2
  - 5 → 3
  - 6 → 3
  - 7 → 4
- **Counting** (SM s 60(2)–(4); s 64(4)):
  - each voting member present (in person or electronically) counts as 1;
  - a member holding a valid proxy counts as **2**;
  - non-voting members don't count;
  - **debtor members DO count** towards quorum.

### Who chairs
- The chairperson, if present (in person or electronically) (SM s 59(1)).
- Otherwise, a member chosen by the voting members present, with that member's agreement (SM s 59(2)).

### How decisions are made
- A motion passes on a **majority of the votes of voting members present and entitled to vote who actually vote** (SM s 65(2)).
- "Present" includes by proxy and electronic means (SM s 65(6)).
- It is a committee decision only if a quorum is present (SM s 65(3)).
- Each voting member has **1 vote**, regardless of how many positions they hold (SM s 65(4), (5)).
- **No casting vote. A tie means the motion is lost.**
  - The SM has no casting-vote provision.
  - BCCM-Office: "If there is a tied vote, the motion is lost" ("Committee voting", updated 30 Apr 2024).
- **Not entitled to vote:**
  - a **debtor member**: anyone who owes a body corporate debt at the time of the meeting, or whose nominating entity does. They can't vote in their own right or as a proxy, and their proxy holder can't vote for them (SM s 64);
  - a member with a **declared conflict** on that issue (SM s 66(2)).

### Proxies (committee)
- A proxy must be **another voting member** (SM s 122(1)).
- Each voting member can hold only **1** proxy at a meeting (SM s 122(2)(b)).
- The **secretary or treasurer** may appoint a proxy **only with committee approval** (SM s 122(2)(a)).
- The proxy must be in the **approved form**, in English, revocable, not transferable, and name an individual (SM s 123).
- It must be given to the **secretary before the meeting starts**. The body corporate or committee can set an earlier deadline, but not more than 24 hours before the meeting (SM s 121(4)).
- It is valid for **1 meeting only** (SM s 121(5)).
- A member can be represented by proxy at **no more than 2 meetings** in the committee's year (SM s 125(2)).
- A proxy can't be used if the appointing member attends, or if the scheme is a layered principal scheme (SM s 124(2)).
- The body corporate may ban or limit proxies by **special resolution** (SM s 121(2)).
- It is an offence to use a proxy knowing you have no right to (maximum penalty 100 penalty units) (SM s 126).

### Conflicts of interest
- A member must **disclose to the meeting** any direct or indirect interest in an issue being considered, or about to be considered, that could conflict with their duties. They **can't vote** on any motion about that issue (SM s 66(1), (2)).
- A proxy holder must disclose their own interest **and** the absent member's interest (if they know of it). They can't vote as proxy on that issue (SM s 66(3)–(6)).
- The code of conduct also requires disclosure of any conflict of interest (Act sch 1A s 6).
- **UNCONFIRMED:** the law does not say a conflicted member must leave the room. Only voting is barred.

### Minutes
- **Who:** the **committee** must make sure full and accurate minutes are taken (SM s 71(1)(a)).
  - The law does not name a minute-taker. BCCM-Office says the secretary "often" does it.
- **Required contents** (SM s 71(6) "full and accurate minutes"):
  1. date, time and place;
  2. names of the people present and the capacity each attended in;
  3. proxies tabled;
  4. for each **owner-submitted motion**: when it was submitted, who submitted it, the reason if not decided (s 58(6)), and any extension notice given;
  5. for each **animal request**: the date of the request, the animal's details (species, breed if relevant, sex, name), and any conditions on approval;
  6. for each motion voted on: **the exact words**, and the **number of votes for and against**;
  7. correspondence, reports, notices and other documents tabled;
  8. closing time;
  9. details of the next meeting, if scheduled;
  10. the **secretary's name and contact address**.
- **Distribution:** the **secretary** gives a copy to **every committee member** and **every owner**, except owners who have opted out in writing. This must happen **within 21 days after the meeting** (SM s 71(2)–(4)).
  - Give it to owners using the SM s 218 methods (personally, to the address for service, or by an agreed method such as a download link) (SM s 71(5)(a)).
- **Confirmation:** the minutes are confirmed by a motion at the next meeting (SM s 57(3)(a)).
- **Keep forever:** committee minutes are not on any disposal list (SM s 231(1)(i), (3), (4)).

### Acting on a resolution: notice of opposition (Standard Module only)
- Owners of **at least half the lots** (24 of 48) can sign a **notice of opposition** to a committee resolution. It must reach the secretary **within 7 days** after the secretary gives owners the minutes, or the record of a resolution passed outside a meeting (SM s 72(1), (3)).
- The committee may **act on a resolution only if one of these applies** (SM s 73(1)):
  - (a) the 7-day opposition window has closed with no notice of opposition; **or**
  - (b) it is an **emergency** and the cost is within the committee spending limit, or an adjudicator has authorised it; **or**
  - (c) the body corporate has ratified it by ordinary resolution; **or**
  - (d) it is **routine and administrative**, and spending is no more than the greater of $200 or $5 × lots. For 48 lots that is **$240**; **or**
  - (e) it approves an animal request (including a deemed approval).
- A notice of opposition can't be given for items (d) or (e) (SM s 72(2)).
- If challenged, whoever relies on (a) must prove the minutes were **properly given** to every member and owner (SM s 73(2), (3)). **Keep proof of delivery.**

---

## 5. Voting outside a committee meeting (VOCM, "flying minute")

| Step | Rule | Citation |
|---|---|---|
| Who sends | The **secretary**, or another committee member **authorised by a majority of voting members** | SM s 68(4) |
| To whom | **All committee members** (in an emergency, as many as can practicably be reached) | SM s 68(1) |
| Form of notice | **In writing**. In an emergency it may be oral or another suitable form | SM s 68(2) |
| Advice to owners | Advice of the motion goes to **each owner at the same time** the notice goes to members (in an emergency, as soon as practicable). Owners who have opted out of committee advice are excluded | SM s 68(3) |
| What the notice must contain | The **words of the motion** (these become part of the record of motions). If the motion is for spending above the major spending limit that the committee may approve, copies of at least **2 quotes** must be attached. **UNCONFIRMED:** the law sets no other required contents. Including the closing date, how to vote and the 21-day rule is good practice | SM s 68; s 71(6) "record of motions" (d); s 174(4) |
| How votes are cast | **In writing**. In an emergency they may be oral or another suitable form | SM s 69(1)(a) |
| Time to vote | **21 days after the notice is given**. For an **animal request**, 21 days after **the request was made to the committee**, not after the notice | SM s 69(1)(b) |
| Who can vote | Voting members **entitled** to vote. Excluded: **debtor members** and **members with a declared conflict** | SM s 67; s 70 (applies s 66(1), (2)) |
| Passed | A **majority of ALL members entitled to vote** agree within the period. This means a majority of everyone entitled, not just of those who replied | SM s 69(2)(a); BCCM-Office "Committee voting" |
| Defeated | **Half or more** of all members entitled to vote do **not** agree within the period | SM s 69(2)(b) |
| Not enough votes by the deadline | A normal motion is **taken to be not agreed to**. An **animal request** is **taken to be APPROVED** (deemed approval) | SM s 69(3) |
| Notice to the animal requester | Written notice that the request is decided, as soon as practicable after the decision, or after the period ends if deemed | SM s 69(4) |
| Record | A **record of motions**: the words, the date the notice was given, the names of the members it was given to, the names of those who voted, and the number for and against. For owner-submitted or animal motions, also the extra details listed in section 4 | SM s 71(1)(b), (6) "record of motions" |
| Give record to owners | The **secretary** gives a copy to **every committee member and owner** (except owners who opted out) **within 21 days** after the motion is decided, or after the day it is taken to be not agreed to | SM s 71(2)–(4) |
| Confirm | The motion **must be confirmed at the next committee meeting**, and the agenda must include that confirmation | SM s 68(5); s 57(3)(b) |
| Acting on it | Same rule as meeting resolutions: wait for the **7-day notice of opposition** window after the record is given, unless an exception applies | SM s 72(3); s 73 |
| Keep | The VOCM notice and members' replies are "associated committee meeting material" and can be disposed of after **2 years** | SM s 231(1)(m), (4)(a), (6) |

### Decision logic (pseudo-code)
```
E = count(voting members) - count(debtor members) - count(members who declared a conflict)
yes > E/2                       -> PASSED       (can be decided before day 21)
no  >= E/2                      -> DEFEATED     (can be decided before day 21)
day 21 reached, neither of above:
    animal request              -> DEEMED APPROVED
    otherwise                   -> NOT AGREED TO
```

---

## 6. Limits on what the committee can decide, and owner applications

### Restricted issues: the committee CANNOT decide these (SM s 52; Act s 100(2))
1. Fixing or changing **levies or contributions**.
   - Exception: the committee may set an **interim** levy before the AGM, based on last year's levels (SM s 162(3)).
2. Changing owners' **rights, privileges or obligations**.
3. Any issue the body corporate has **reserved by ordinary resolution**. These must be listed in the register of reserved issues, and a copy goes with each AGM notice (SM s 230).
4. Anything that needs a resolution without dissent, special, majority or ordinary resolution.
5. **Starting legal proceedings**, except:
   - recovering a liquidated debt from an owner;
   - counterclaims or related proceedings where the body corporate is already a party;
   - by-law offence proceedings under Act ch 3 pt 5 div 4;
   - a dispute resolution application under Act ch 6 (but not an appeal against an adjudicator's order).
6. **Paying committee members** remuneration, allowances or expenses, unless one of these applies (SM s 53):
   - an ordinary resolution states the full amount and the reason, with an explanatory schedule; **or**
   - it reimburses **$50 or less** of costs for attending a committee meeting, **and** the member's total for meeting-attendance costs is no more than **$300 in any 12 months**.

### Spending limits (48 lots)

| Limit | Default for Alatai | Rule | Citation |
|---|---|---|---|
| **Committee spending limit** | **$9,600** ($200 × 48), **including GST** | Can be changed by ordinary resolution at a general meeting. The committee may spend over it only if: ordinary resolution authorises it; all owners consent in writing; an adjudicator authorises it for an emergency; it is needed to comply with a statutory order, adjudicator order, court order or QCAT order; or it is to place or renew required insurance (if that isn't a restricted issue). **A single project can't be split** to fit under the limit. The money must be in the budget | SM sch 1; s 172; BCCM-Office "Committee spending" (GST, splitting, budget) |
| **Major spending limit** | **$10,000** (the lesser of $1,100 × 48 = $52,800 and $10,000) | A **general-meeting** motion above this needs **at least 2 quotes** sent with the notice. A **committee** decision above this (only possible if the committee limit has been raised above $10,000) needs 2 quotes to be considered, or attached to the VOCM notice. Quotes are kept with the minutes | SM sch 1; s 173; s 174 |
| **Routine admin carve-out** | **$240** (the greater of $200 and $5 × 48) | Can be acted on straight away; no opposition window | SM s 72(2)(a); s 73(1)(d) |
| **Body corporate improvements** | Basic limit **$14,400** ($300 × 48). But the **committee** is still capped by its **$9,600** spending limit | Ordinary resolution range: up to $96,000 ($2,000 × 48), once per financial year. Above that needs a special resolution | SM s 186; BCCM-Office "Improving common property and lots" |
| **Borrowing** | $12,000 ($250 × 48) | Borrowing needs an ordinary resolution. Being in debt above $12,000 needs a resolution without dissent | SM s 171 |

### Owner applications the committee must decide

| Application | Who receives it | Deadline | If nobody decides | Other rules | Citation |
|---|---|---|---|---|---|
| **Animal (pet) request**, where the by-law says committee approval is needed | Secretary, or the chairperson if the secretary is absent (or a BCM holding the secretary's powers) | **21 days after the request is made** | **Deemed APPROVED**. Written notice to the requester as soon as practicable after the 21 days | Must be decided as a committee motion. May attach **reasonable conditions**. **Must not unreasonably refuse.** "No pets allowed" is an unreasonable ground. Refusal is allowed only on the grounds in Act s 169B(6): unacceptable health or safety risk that conditions can't manage; contravenes a law; a **regulated dog**; unreasonable interference with other occupiers or native fauna that conditions can't manage; or the owner refuses reasonable conditions. Approval can be withdrawn if conditions are breached. Assistance dogs are excluded. No notice of opposition, and the committee can act immediately | SM s 58A, 58B; s 69(1)(b)(ii), (3)(b); Act s 169B; SM s 72(2)(b); s 73(1)(e); BCCM-Office "Animal by-laws" (updated 18 May 2026) |
| **Animal request that must go to a general meeting** (a restricted issue, for example a reserved issue) | Secretary, or the chair if the secretary is absent | Call a general meeting **within 21 days** of the request, with the request as an agenda motion. Decide it **within 6 weeks after the meeting notice** | **Deemed APPROVED** if no meeting is called in 21 days, or no decision is made in 6 weeks. Record the deemed decision in the minutes of the next general meeting | | SM s 82A, 82B |
| **Any other owner motion to the committee** (for example, by-law approvals such as flooring or renovations; requests for action) | Secretary (personally, by post, fax or electronic means) | Decide **within 6 weeks** of submission (the "decision period"). Or, **before 6 weeks**, give written notice of: the need for more time, the reason, and a new deadline **no more than 6 more weeks** away | **Taken to be NOT agreed to** at 6 weeks (or at the extended date; **12 weeks** maximum from submission) | The committee **need not decide** it if, in the previous 12 months, the owner submitted a motion on the same issue or 6 or more motions; it must then tell the owner why in writing. The committee **must not decide** it if it is a restricted issue, conflicts with the Act, regulation, by-laws or a motion already voted on, or is unlawful or unenforceable. The reason goes in the minutes or record. Note the 12-week wording: s 58(7)(b) counts "12 weeks after the day the motion is given to the secretary" | SM s 58; s 71(6) |
| **Owner improvement to common property** (for the owner's lot) | Body corporate (committee, if within its powers) | **No statutory deadline** that I found. If submitted as a motion, the 6-week s 58 timetable applies (**UNCONFIRMED** that every request is a s 58 motion; it depends on how it is lodged and the by-law wording) | Taken to be not agreed to under s 58(7), if lodged as a motion | The committee can approve it without a general meeting **only if**: installed value **$3,000 or less**; it doesn't detract from the appearance of any lot or common property; and it is unlikely to lead to a breach of occupier duties. Otherwise it needs an **ordinary resolution**. Conditions may be imposed. The owner must maintain it. Record it in the **register of authorisations** | SM s 187; s 228(3), (4); BCCM-Office "Improving common property and lots" (updated 7 Jan 2026) |
| **Owner motion for a general meeting** | Secretary | Put on the **next practicable** general meeting agenda. For the AGM, it must reach the secretary **before the financial year ends**. Owners must be invited to submit motions with the nomination notice | n/a | The owner's wording must go on the voting paper unchanged. The owner's explanatory note can be up to 300 words (BCCM-Office "Submitting a body corporate motion", updated 20 Oct 2026). Certain motion types are limited to once per financial year | SM s 86(5)–(8); BCCM-Office |
| **Requested EGM** (owners of 25% of lots = **12 of 48**) | Secretary, or the chair if the secretary is absent | **Call within 14 days. Hold within 6 weeks.** At least 21 days' notice | If not called in 14 days, the requesters can ask another committee member, who must call it within 14 days | | SM s 84, 85, 91 |
| **Records inspection or copies** | Body corporate | **7 days** after a written request **plus the fee** | Offence (max 20 penalty units) | See section 7 | Act s 205(2) |
| **Body corporate certificate** | Body corporate | **5 business days** after the request plus the fee. Optional **24-hour** priority service (fee refunded if late) | Offence | | Act s 205(4)–(6); SM s 233(3)–(5) |

---

## 7. Records

### What must be kept (SM s 231(1); Act s 204)
The body corporate must keep (the secretary or BCM in practice; **UNCONFIRMED**, because the law puts this on "the body corporate", not a named position):
- accounting records and annual statements of account;
- notices from authorities (council, government);
- orders against the body corporate (adjudicator, court);
- every insurance policy;
- documents for each engagement of a BCM or service contractor and each letting agent authorisation;
- exclusive-use agreements with owners;
- authorisations to occupy or use common property;
- **all correspondence sent and received**;
- **all committee minutes** and associated material;
- **all general meeting minutes** and associated material;
- reports from a ch 3 pt 5 BCM;
- monthly reconciliation statements, with the bank statements and invoices;
- **VOCM notices and members' responses**.

### Rolls and registers
| Record | Contents | Deadline | Citation |
|---|---|---|---|
| **Roll** | Original owner; lot entitlements; each owner's name, address and address for service; ACN or ARBN; mortgagees in possession; notices given (owner changes, leases of 6 months or more, letting agent engaged or ended, nominees, representatives) | Record new information **within 14 days** of receiving it | SM s 224, 225 |
| Register of assets | Assets over $1,000: description, purchase or gift, date, cost or value, supplier or donor | n/a | SM s 226 |
| Register of engagements | BCM, service contractors, letting agent: duties, pay basis, term, **BCM's delegated executive powers**, and an original signed contract | n/a | SM s 227 |
| Register of common property authorisations | Contractor occupation; **owner improvements** (date, area, conditions, any adjudicator order) | n/a | SM s 228 |
| Register of exclusive use allocations | If applicable | n/a | SM s 229 |
| **Register of reserved issues** | Description and date of the resolution. **A copy goes with every AGM notice** | n/a | SM s 230 |

### How long (SM s 231(3)–(5))
- **6 years**, then may be destroyed:
  - statements of account and audit certificates;
  - meeting notices and agendas;
  - major repair or installation records;
  - orders;
  - authority notices;
  - written agreements;
  - ch 3 pt 5 BCM reports.
- **2 years**, then may be destroyed:
  - associated committee material (notices, proxies, VOCM notices and replies, opposition notices, resignations, agreements to shorten notice);
  - associated general meeting material (other than notices of meetings);
  - insignificant correspondence;
  - reconciliations, bank statements and invoices.
- **Never destroy** anything still relevant, for example a contract running longer than 6 years, or a notice whose information is still current.
- **Not on any disposal list, so keep permanently:**
  - committee and general meeting **minutes**;
  - the roll and registers;
  - insurance policies;
  - significant correspondence;
  - general accounting records.
  - **UNCONFIRMED:** "permanent" is my reading. The regulation only lists what *may* be destroyed. Tax-law retention rules are outside this document.
- Minutes, the roll and registers may be kept in electronic image form (SM s 231(2)).

### Who can see records, and when

| Who | Right | Deadline | Fee (indexed; from 1 Jul 2026) | Citation |
|---|---|---|---|---|
| **Committee members** | "Reasonable access" | No fixed time ("reasonable") | **Free** | SM s 232(1) |
| **Owner** of a lot | Inspect and/or get copies | **7 days** after the written request plus fee | Inspection **18.25 fee units = $20.70**. Copies **0.65 fee units/page = $0.75/page**. Copies only = no inspection fee | Act s 205(2), (13); SM s 233(1); BCCM-Office "Fees for accessing body corporate records" (updated 1 Jul 2026) |
| **Tenant / occupier** | **Only if** they satisfy the body corporate of a **"proper interest"** (BCCM-Office example: a tenant wanting information about living in or using the lot). Otherwise no right | 7 days, once accepted | Non-owner inspection **35.10 fee units = $39.75**. Copies $0.75/page | Act s 205(13)(e); SM s 233(1)(a)(ii); BCCM-Office "Accessing your body corporate's records" (updated 1 Jul 2024) |
| Mortgagee, buyer, person given a disclosure statement, or an agent of any of these | Inspect and/or copies | 7 days | Non-owner rates | Act s 205(13) |
| Interested person asking for a **body corporate certificate** | Certificate in the approved form (BCCM Form 33) | **5 business days**; priority 24 hours | **76.75 fee units = $86.95**. Repeat within 3 months **65.24 = $73.90**. Priority **+27.35 = $31**, refunded if late | Act s 205(4)–(6); SM s 233(2)–(5); BCCM-Office fees page |

Access rules:
- **How inspection happens:** the way agreed with the requester; otherwise in person, at a **reasonable time and place** the body corporate chooses (Act s 205(2)(a)).
- **How copies are sent:** the way agreed; otherwise by **post or personal delivery** (Act s 205(2)(b); SM s 233A).
- **No other charges:** the body corporate can't add other charges, such as for the manager's time (BCCM-Office fees page).
- **No GST** on these fees (BCCM-Office fees page).
- **Refusal is allowed only for:**
  - parts the body corporate reasonably believes are **defamatory** (Act s 205(3); SM s 232(3));
  - for committee members, **legally privileged** records where a proceeding with that member has started or is threatened (SM s 232(2)).
- **Privacy law is not a ground** to refuse records the law requires to be given (BCCM-Office "Accessing your body corporate's records").
- **Fee dollar amounts change every 1 July.** Store fees as **fee units × the current fee-unit value**, not as fixed dollars.

### Return of records
- Anyone holding body corporate records or assets in their role must hand them over **within 14 days** of a committee resolution notice naming the recipient (SM s 235).
- Penalty: maximum 20 penalty units.
- No lien can be claimed on documents.

---

## 8. Rules the software should enforce

Format: **Trigger → Required action → Who → Deadline → Citation**.

Counting days:
- Exclude the trigger day (AIA s 38(1)).
- "At least N days" notice means N **clear** days (also exclude the meeting day) (AIA s 38(1)(a)).
- If a forward deadline falls on a weekend or public holiday, move it to the next business day (AIA s 38(2), (5)).
- **UNCONFIRMED:** that the AIA applies to the SM through the Statutory Instruments Act 1992. I did not re-read that Act.

### Scheme setup
1. **Scheme created** → require `regulation_module`, taken from the current CMS, before committee features turn on → Admin → before go-live → Act s 21; SM s 233AA(1)(b)(ii).
2. **Scheme setup** → store the limits: committee spending ($9,600 default), major spending ($10,000), routine admin ($240), owner minor improvement ($3,000), basic improvement ($14,400). Allow them to be overridden **only by a recorded ordinary resolution** → Admin → on any change → SM sch 1; s 72(2); s 186; s 187(5).

### Committee make-up
3. **Committee roster saved** → block if: fewer than 3 voting members; more than 7; no chair, secretary or treasurer; 2 voting members holding seats for the same lot; or a voting member who is a BCM, contractor or letting agent (or their associate) → System → on save → SM s 9(2), (4); s 10(2); s 11; sch 1.
4. **One person holds 2 or 3 executive positions** → allow, but give **1 vote only** → System → always → SM s 9(3); s 65(5).
5. **BCM or caretaker engaged** → add them as a **non-voting** member. Exclude them from quorum and votes. Send them meeting notices → System → on engagement → SM s 12; s 55(1); s 60(3).
6. **Member misses a 2nd consecutive meeting without recorded leave** → flag the position as **vacant** → Secretary to confirm → at that meeting's close → SM s 44(2)(d).
7. **Position vacant** (any reason in SM s 44(2)) → appoint an eligible person, or call a general meeting. If below quorum, a general meeting is mandatory, with the s 49 explanatory note and a ch 3 pt 5 BCM motion on the agenda → Committee → **1 month** → SM s 48, 49, 51.
8. **AGM leaves an executive position unfilled, or fewer than 3 members** → call an EGM → elected members → **call within 1 month; hold within 2 months** of the AGM → SM s 41.

### Committee meetings
9. **Committee meeting scheduled** → send written notice and agenda to all committee members (including non-voting) **at least 7 clear days** before. Allow 2 days **only** if all voting members agreed (record the vote or written consents) → Secretary (chair if absent) → 7 or 2 days before → SM s 55(1), (2).
10. **Same trigger** → send the advice and agenda to **every owner not opted out**, and post it on the noticeboard, **at the same time** as the committee notice → Secretary → same day as committee notice → SM s 55(3), (4).
11. **Agenda built** → auto-add "Confirm minutes of previous meeting" and "Confirm each VOCM resolution since last meeting" → Secretary → before notice → SM s 57(3).
12. **Written request from a quorum of members** → call a meeting. If no meeting is held within 21 days, let any member call it with a quorum's agreement → Secretary (chair if absent) → **held within 21 days** → SM s 54(2)–(4).
13. **Owner asks to attend** → accept only if received **at least 24 hours before** the meeting (representatives also need address, category, owner's name and evidence) → Secretary → 24 h before → SM s 63(2), (3).
14. **Proxy lodged** → validate: the holder is a voting member; the holder has no other proxy for this meeting; secretary or treasurer appointments have committee approval; the appointer has used no more than 2 proxies this year; approved form; lodged before the meeting starts (or the set cut-off, at most 24 h before) → Secretary → before start → SM s 121(4), (5); s 122; s 123; s 125(2).
15. **Meeting opens** → compute quorum = ceiling(voting members ÷ 2). Proxy holders count as 2; debtors count; non-voting members don't. Block the "decision" status if there is no quorum → Chair → at open and on each vote → SM s 60; s 64(4); s 65(3).
16. **Each motion** → before voting, prompt every voting member and proxy holder to **declare conflicts**. Remove conflicted members and **debtor members** from the eligible voter list → Chair → before each vote → SM s 64; s 66; Act sch 1A s 6.
17. **Vote tallied** → PASS if yes > no among those voting. **Tie = LOST.** No casting vote → System → at vote → SM s 65(2); BCCM-Office "Committee voting".
18. **Motion touches a restricted issue** → block the committee from deciding it. Route to a general meeting → System → at agenda build and vote → SM s 52; s 58(6)(a); Act s 100(2).
19. **Payment to a committee member** → block, unless: it is an attendance reimbursement of $50 or less **and** the 12-month total is $300 or less; or there is an ordinary resolution with an explanatory schedule → Treasurer or BCM → before payment → SM s 52(1)(f); s 53.

### Minutes and acting on decisions
20. **Meeting closed** → minutes must contain all of the SM s 71(6) fields (including exact motion wording, votes for and against, and the secretary's name and address). Block "issued" status until they are complete → Committee (minute-taker) → before issue → SM s 71(1), (6).
21. **Meeting held** → send minutes to all committee members and all owners not opted out → Secretary → **within 21 days** after the meeting → SM s 71(2)–(5).
22. **Minutes or VOCM record issued** → open a **7-day notice-of-opposition window** per resolution. Block "actioned" status until it closes, **unless** the resolution is flagged as: emergency within the spending limit; ratified by ordinary resolution; routine admin of $240 or less; or an animal approval. Keep delivery proof for every recipient → System / Secretary → **7 days** after issue → SM s 72; s 73.
23. **Notice of opposition received** signed for **24 or more lots** (half of 48) → mark the resolution **blocked**. It can be actioned only by ordinary resolution at a general meeting (or under another SM s 73 exception) → Secretary → on receipt → SM s 72(1); s 73(1)(c).

### Spending
24. **Spending proposal** → total the whole project, including GST. If it is over the committee limit ($9,600), block committee approval unless an SM s 172(1) exception is recorded → Treasurer / Committee → before approval → SM s 172; BCCM-Office "Committee spending".
25. **Spending proposal above the major spending limit ($10,000)** → require **2 or more quotes** (or 1, with a recorded "exceptional reason"). Attach them to the general meeting notice or VOCM notice, and keep them with the minutes → Committee / Secretary → before the decision or notice → SM s 173; s 174.

### Voting outside a meeting (VOCM)
26. **VOCM created** → send the written motion to **all** committee members, and send the owner advice **at the same time** (except in an emergency). The sender must be the secretary or a member authorised by a majority → Secretary → on send → SM s 68.
27. **VOCM running** → eligible voters = voting members minus debtors minus declared-conflicted members. Close early: PASS when yes > half of eligible; FAIL when no ≥ half of eligible → System → continuously → SM s 67; s 69(2); s 70.
28. **VOCM reaches day 21** with no result → mark it **NOT AGREED TO**. For an animal request, mark it **DEEMED APPROVED** (21 days counted from the **request date**) and notify the requester → System / Secretary → day 21 → SM s 69(1)(b), (3), (4).
29. **VOCM decided** → issue the **record of motions** (words, date sent, recipients, voters, votes for and against) to all members and owners not opted out. Also add a confirmation item to the next meeting's agenda → Secretary → **within 21 days** of the decision → SM s 68(5); s 71(2), (4), (6).

### Owner applications
30. **Owner motion received by the secretary** → timestamp it and start a **6-week** clock. The committee decides it, or sends a written extension notice (reason plus a new date no more than 6 more weeks away) before the 6 weeks end → Committee / Secretary → 6 weeks (12 weeks maximum) → SM s 58(2), (3).
31. **Owner motion clock expires** → mark it **taken to be NOT agreed to**, record it in the record of motions, and send it out within 21 days → System / Secretary → at expiry; then 21 days → SM s 58(7); s 71(4)(b)(ii).
32. **Owner motion received** → check the owner's history over the previous 12 months: a motion on the same issue, or 6 or more motions. If so, the committee **may** decline, but must send written reasons → Secretary → within the decision period → SM s 58(4), (5).
33. **Animal request received** (committee-approval by-law) → start a **21-day** clock from the request date. Decide it, with any reasonable conditions. Allow refusal only with an Act s 169B(6) ground selected; block "no pets" as a ground. At day 21 with no decision → **DEEMED APPROVED**, and send written notice → Secretary (chair if absent) / Committee → **21 days** → SM s 58A; s 58B; Act s 169B(4)–(6).
34. **Animal request that must go to a general meeting** → call the general meeting and put the request on the agenda. Deemed approved if the meeting isn't called within 21 days, or no decision is made within 6 weeks of the notice. Record a deemed decision in the minutes of the next general meeting → Secretary / Committee → **21 days** to call; **6 weeks** to decide → SM s 82A; s 82B.
35. **Owner improvement request** → if $3,000 or less installed **and** the committee confirms "no detraction from appearance" **and** "unlikely to breach occupier duties", the committee may approve with conditions. Otherwise route it to an ordinary resolution at a general meeting. On approval, write it to the common property authorisations register → Committee / Secretary → no statutory deadline (use the 6-week s 58 clock if lodged as a motion) → SM s 187; s 228(3), (4).

### Records and general meetings
36. **Records request plus fee received** (owner or other interested person) → provide copies, or offer an inspection time and place → Secretary / BCM → **7 days** → Act s 205(2).
37. **Records request from a tenant or other non-owner** → require the "proper interest" to be stated and recorded before accepting; charge non-owner fees → Secretary / BCM → 7 days after acceptance plus fee → Act s 205(13)(e); SM s 233(1).
38. **Committee member asks to see records** → give reasonable access, free → Secretary / BCM → reasonable time → SM s 232(1).
39. **New information for the roll** (sale, lease of 6 months or more, address change, nominee) → update the roll → Secretary / BCM → **14 days** → SM s 224; s 225.
40. **Disposal job runs** → only destroy items in the SM s 231(3) list (after 6 years) or s 231(4) list (after 2 years) that are flagged "no current relevance". Never destroy minutes, the roll, registers or policies → Secretary / BCM → yearly → SM s 231.
41. **Six weeks before financial year end** → secretary sends the nomination notice (with motion invitation and debtor warning) to every owner on the roll. Allowed window: 6 to 3 weeks before the end of the financial year → Secretary → **at least 3 weeks before** FY end → SM s 16(2), (3); s 86(8).
42. **Financial year ends** → AGM called and held → Committee / Secretary → **within 3 months** → SM s 83.
43. **Requested EGM** received (owners of 12 or more lots) → call it → Secretary (chair if absent) → **call within 14 days; hold within 6 weeks**; at least 21 days' notice → SM s 84; s 91.
44. **Levy instalment due** → send the contribution notice → Treasurer / BCM (body corporate duty) → **at least 30 days before** the due date → SM s 163.

---

## Points to verify with the owners or the BCM (not legal questions)
- **The CMS module for Alatai.** Standard or Accommodation? If it is Accommodation, the notice-of-opposition rules (8.22–8.23) do not apply, and every citation must be re-mapped.
- Whether a BCM is engaged, and **which executive powers** it holds (Act s 119). Check the register of engagements (SM s 227(2)(d)).
- Whether the body corporate has passed ordinary resolutions that change:
  - the committee spending limit or major spending limit;
  - monthly reconciliations;
  - electronic voting;
  - open ballots;
  - reserved issues;
  - proxy bans.
- The **animal by-law wording**: committee approval or general meeting approval.
- Whether there is a **caretaking service contractor**. If so, it is a non-voting committee member.
