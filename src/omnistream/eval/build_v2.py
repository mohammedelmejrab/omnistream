"""Reproducibly author the v2 fictional corpus; never modifies v1."""

import json
from pathlib import Path

ROWS = [
    (
        "Halvex Mobility",
        "HVM",
        "Iona Pelwick",
        "Sefu Daram",
        "Cobalt Reach Laboratory",
        "CRL",
        "Wispcoil",
        "brake seal",
        8.4,
        "Halvek Materials",
    ),
    (
        "Nacreline Systems",
        "NLS",
        "Omar Vesk",
        "Leda Quorin",
        "Juniper Basin Institute",
        "JBI",
        "Morrowcell",
        "coolant valve",
        31.7,
        "Nacrelane Services",
    ),
    (
        "Brindle Arc",
        "BDA",
        "Talia Muren",
        "Kofi Zelan",
        "Sable Meridian Centre",
        "SMC",
        "Kiteglass",
        "battery latch",
        6.25,
        "Brindle Arch",
    ),
    (
        "Oxbriar Robotics",
        "OBR",
        "Neri Solvek",
        "Pia Ashuno",
        "Ivory Delta Laboratory",
        "IDL",
        "Thistledrive",
        "sensor housing",
        42.9,
        "Oxbrier Logistics",
    ),
    (
        "Vespergate Works",
        "VGW",
        "Arun Kelso",
        "Zora Fendel",
        "Copper Fen Institute",
        "CFI",
        "Rillmesh",
        "pressure relay",
        12.6,
        "Vespergait Foods",
    ),
    (
        "Quenara Devices",
        "QND",
        "Mina Tolvik",
        "Eben Rusk",
        "Indigo Vale Centre",
        "IVC",
        "Emberfoil",
        "steering pin",
        27.3,
        "Quenaro Digital",
    ),
    (
        "Tesselmere Controls",
        "TMC",
        "Yara Penlo",
        "Davi Ornek",
        "Opal Ridge Laboratory",
        "ORL",
        "Driftloom",
        "power connector",
        5.8,
        "Tesselmar Construction",
    ),
    (
        "Aldervane Transit",
        "AVT",
        "Sana Ulrich",
        "Remi Basun",
        "Ochre Hollow Institute",
        "OHI",
        "Glimmerpod",
        "axle collar",
        19.45,
        "Aldervain Travel",
    ),
    (
        "Pellucid Forge",
        "PCF",
        "Enzo Nalik",
        "Ada Wurfen",
        "Violet Strand Centre",
        "VSC",
        "Frostweave",
        "motor bearing",
        37.2,
        "Pellucent Foundry",
    ),
    (
        "Ravenspire Instruments",
        "RSI",
        "Jori Anvek",
        "Uma Cevran",
        "Silver Marsh Laboratory",
        "SML",
        "Pebbleflux",
        "control fuse",
        14.15,
        "Ravenspear Insurance",
    ),
]
ITEMS = []
QUESTIONS = []


def item(n, kind, title, text, bubble, date, fresh=False):
    row = {
        "id": f"{n}-{kind}",
        "title": title,
        "text": text,
        "published_at": f"2026-{date}T12:00:00+00:00",
        "source": ["Wire Desk", "Market Ledger", "Methods Review"][
            ["News", "Finance", "Research"].index(bubble)
        ],
        "credibility": 0.92,
        "url": f"https://fictional-v2.invalid/{n}/{kind}",
        "bubbles": [bubble],
        "freshness": fresh,
        "routing_label": [bubble],
    }
    assert 80 <= len(text.split()) <= 250, (row["id"], len(text.split()))
    # Scenario-specific editorial detail and alternating structures keep source prose varied.
    details = [
        "The archive uses signed paper minutes and a separately maintained electronic index.",
        "A regional editor checked the figures against the board's original supporting schedule.",
        "The report was prepared for an industry newsletter with a focus on supply reliability.",
        "Reviewers requested a correction log so that readers can distinguish later amendments.",
        "A public webcast accompanied the release; its transcript is retained by the publisher.",
        "The publisher included a glossary for readers unfamiliar with the technical terminology.",
        "The source was circulated to employees before distribution to subscribing analysts.",
        "Local correspondents compared the statement with the register held by the company secretary.",
        "An appendix describes the document's scope and excludes figures from affiliated businesses.",
        "The editor retained the dated attachments rather than combining them with previous notices.",
    ]
    row["text"].split(". ")
    # Distinct editorial formats: summary first, quoted extract, dated log, or background first.
    if n % 4 == 1:
        row["text"] = "From the editor: " + details[n] + "\n\n" + row["text"]
    elif n % 4 == 2:
        row["text"] = (
            "Document extract / " + row["text"] + "\nEditorial context: " + details[n]
        )
    elif n % 4 == 3:
        row["text"] = details[n] + "\nRecord summary: " + row["text"]
    else:
        row["text"] += "\n" + details[n]
    ITEMS.append(row)


def question(n, kind, text, answer, gold, bubbles, facts=None):
    QUESTIONS.append(
        {
            "id": f"v2-q{len(QUESTIONS) + 1:02}",
            "type": kind,
            "question": text,
            "reference_answer": answer,
            "key_facts": facts or [answer],
            "gold": [f"{n}-{g}" for g in gold],
            "expected_bubbles": bubbles,
        }
    )


for n, (co, alias, old, new, lab, short, prod, defect, amount, decoy) in enumerate(
    ROWS
):
    item(
        n,
        "leader",
        "Board register: executive appointment",
        f"""The board of {co} appointed {old} as chief executive effective January 12. In its corporate register the manufacturer also uses the trading abbreviation {alias}. The appointment carries responsibility for operational safety, supplier relations and quarterly reporting. Directors approved the appointment at a closed meeting and released the voting record afterwards. The incoming executive signed a mandate covering the full operating business, rather than a regional division. The register lists the appointment date separately from the publication date. An independent secretary countersigned the entry and archived the appointment letter with the annual governance documents.""",
        "News",
        "01-13",
    )
    item(
        n,
        "recall",
        f"Safety wire: {defect} recall",
        f"""SAFETY WIRE / September 9. {co} recalled its vehicle modules after inspectors identified a defective {defect}. The chief executive resigned following the recall on September 11. The notice refers to that officer as the {alias} chief and does not name a replacement. Shipments from the affected assembly line were suspended pending inspection. Customers were offered replacement parts and a dedicated telephone service. The board established a safety committee to examine the supplier records. Directors said that the resignation and the recall were separate resolutions adopted during the same emergency meeting. Export deliveries remained suspended through the weekend.""",
        "News",
        "09-12",
    )
    item(
        n,
        "appointment",
        "Minutes from the extraordinary board meeting",
        f"""Resolution adopted September 18: {new} is appointed chief executive of {co}, effective at the close of this meeting. The appointee accepts responsibility for rebuilding safety procedures after the September recall. An interim operations committee will transfer signing authority over the following two business days. No merger or change of ownership forms part of this resolution. The directors instructed the company secretary to record the effective date and circulate a signed copy to employees. The appointment applies to the parent company and all manufacturing divisions. A separate remuneration resolution will be considered at the next scheduled meeting.""",
        "News",
        "09-19",
    )
    item(
        n,
        "funding",
        "Research allocation in the investment ledger",
        f"""ANALYST NOTE. {alias}, the listed abbreviation used by {co}, signed a research funding agreement with {lab} ({short}) on February 7. The commitment is {amount} million crowns, payable in three tranches subject to audited spending. It is a grant rather than an equity purchase, and gives the sponsor no ownership of the laboratory. Payment conditions concern laboratory equipment, staff costs and independent measurement. The recipient must retain experimental records for inspection. Unused funds return to the sponsor after the project closes. The note distinguishes the committed amount from the smaller first cash installment and excludes unrelated charitable donations.""",
        "Finance",
        "02-08",
    )
    item(
        n,
        "study",
        f"{prod}: a laboratory methods abstract",
        f"""ABSTRACT. Investigators at {short} report development of {prod}, an experimental energy membrane. In controlled trials the prototype retained its structure after repeated thermal cycling. The methods section specifies a sealed chamber and independent instrument calibration before each batch. Researchers randomized the order of samples and kept a separate control group. The reported result concerns laboratory performance, with no claim of commercial readiness or vehicle approval. Replication data will be retained by the institute and released to collaborating researchers on request. The authors distinguish membrane durability from conversion efficiency and recommend further outdoor trials before any manufacturing decision.""",
        "Research",
        "04-17",
    )
    if 2 <= n < 7:
        study = ITEMS[-1]
        study["text"] += (
            f" Visiting fellow {old} supervised the instrument calibration; the fellowship is separate from any corporate board position."
        )
    elif n >= 7:
        ITEMS[-1]["text"] += (
            f" Dovetail Quay {n + 1} supplied the sealed chamber used by {short}; equipment ownership stayed with the institute."
        )
    item(
        n,
        "deal",
        "Proposed acquisition: filing summary",
        f"""The investment filing dated June 3 records {co}'s agreement to acquire a controlling stake in the instrument supplier Dovetail Quay {n + 1}. Completion is conditional on competition clearance and lender consent. The parties signed a provisional purchase agreement with a refundable deposit. The announced consideration includes cash and a deferred component tied to delivery performance. Analysts should distinguish a signed agreement from a completed transfer of ownership. Neither company has consolidated the other's accounts. The filing sets an October deadline for the required consents and allows either party to withdraw if the conditions fail.""",
        "Finance",
        "06-04",
    )
    item(
        n,
        "cancel",
        "Transaction termination notice",
        f"""Filing update, October 6. {co} and Dovetail Quay {n + 1} terminated their June purchase agreement after the lenders declined consent. The refundable deposit will be returned within ten business days. No shares were transferred under the agreement and the supplier remains independent. Each party will bear its own advisory costs. The termination releases both companies from the proposed closing obligations. Management declined to announce a replacement transaction. Accountants will expense the due diligence work in the next reporting period. The notice identifies the signed June agreement precisely to avoid confusion with ordinary supply contracts that continue between the parties.""",
        "Finance",
        "10-07",
    )
    code = [
        "AX-49",
        "QD-18",
        "VT-73",
        "BK-26",
        "SM-91",
        "ER-35",
        "UP-62",
        "CW-14",
        "JF-87",
        "NZ-53",
    ][n]
    item(
        n,
        "fresh",
        f"Archive deposit for {prod}",
        f"""DATA DEPOSIT / November 2. The {short} team deposited the replication archive for {prod} under accession {code}. The archive includes instrument settings, anonymized batch measurements and a description of excluded samples. A curator checked that the package could be opened independently of the authors' laboratory software. Readers should use the accession identifier when requesting this particular deposit. The archive is released for replication studies and does not certify commercial product performance. A checksum accompanies each file to detect transmission errors. The institute will preserve earlier versions alongside any corrected uploads so that published analyses remain reproducible.""",
        "Research",
        "11-02",
        True,
    )
    item(
        n,
        "decoy",
        f"{decoy}: investor interview",
        f"""INTERVIEW. A spokesperson for {decoy} rejected suggestions that the firm financed {lab}. "Our similarly named neighbor operates in a different industry," the spokesperson said. "Our September product inspection did not lead to an executive resignation." The firm's expenditure review covered training and office systems, with no research grant to the named institution. An editor checked the registration record and confirmed that the business is legally separate from {co}. The distinction matters because an early market newsletter confused the two businesses. The correction preserves the separate trading names and warns readers against combining their financial statements.""",
        "Finance",
        "10-12",
    )
    question(
        n,
        "single",
        f"How much research funding did {co} commit on February 7?",
        f"{amount} million crowns",
        ["funding"],
        ["Finance"],
    )
    if n < 5:
        question(
            n,
            "single",
            f"Which experimental membrane was developed by {short}?",
            prod,
            ["study"],
            ["Research"],
        )
    question(
        n,
        "multi_hop",
        f"Which research institution received a grant from the manufacturer whose chief resigned following the September {defect} recall?",
        lab,
        ["recall", "funding"],
        ["News", "Finance"],
    )
    if n < 2:
        question(
            n,
            "multi_hop",
            f"What experimental membrane did the laboratory backed by the company affected by the {defect} recall develop?",
            prod,
            ["recall", "funding", "study"],
            ["News", "Finance", "Research"],
        )
    elif n < 7:
        question(
            n,
            "multi_hop",
            f"What membrane did the institution hosting the visiting fellowship of the January-appointed {alias} chief develop?",
            prod,
            ["leader", "study"],
            ["News", "Research"],
        )
    else:
        question(
            n,
            "multi_hop",
            f"Which research institution used the sealed chamber supplied by the proposed acquisition target in the June {co} agreement?",
            short,
            ["deal", "study"],
            ["Finance", "Research"],
        )
    if n < 5:
        question(
            n,
            "time_sensitive",
            f"Who led {co} immediately before the September recall?",
            old,
            ["leader", "recall"],
            ["News"],
        )
        question(
            n,
            "time_sensitive",
            f"As of October 15, did {co} own Dovetail Quay {n + 1} under the June agreement?",
            "No; the acquisition agreement was terminated on October 6 and no shares transferred.",
            ["deal", "cancel"],
            ["Finance"],
            ["terminated", "No shares"],
        )
    else:
        question(
            n,
            "time_sensitive",
            f"Who leads {co} as of October 15?",
            new,
            ["leader", "appointment"],
            ["News"],
        )
    question(
        n,
        "freshness",
        f"What accession identifies the November replication archive for {prod}?",
        code,
        ["fresh"],
        ["Research"],
    )

# Question-only review corrections; item construction remains frozen.
for q in QUESTIONS:
    institution = {
        "v2-q48": "Ochre Hollow Institute",
        "v2-q53": "Violet Strand Centre",
        "v2-q58": "Silver Marsh Laboratory",
    }.get(q["id"])
    if institution:
        abbreviation = q["reference_answer"]
        q["reference_answer"] = f"{institution} ({abbreviation})"
        q["key_fact_alternatives"] = [[abbreviation, institution]]
    if q["id"] in ("v2-q02", "v2-q09", "v2-q16", "v2-q23", "v2-q30"):
        q["acceptable_evidence"] = [q["gold"][0].replace("-study", "-fresh")]

# Present a mixed smoke selection instead of five copies of one question type.
priority = ["single", "multi_hop", "multi_hop", "time_sensitive", "freshness"]
head = []
for kind in priority:
    q = next(q for q in QUESTIONS if q["type"] == kind and q not in head)
    head.append(q)
QUESTIONS = head + [q for q in QUESTIONS if q not in head]
data = {
    "version": "2.0.0",
    "description": "Ten fictional industrial research networks with aliases, unnamed bridges, near-name distractors and dated reversals. All routing labels authored; ten archives held back.",
    "items": ITEMS,
    "questions": QUESTIONS,
    "calibration": [],
}
from omnistream.eval.dataset import validate_dataset

validate_dataset(data)
Path(__file__).with_name("corpus").joinpath("eval-v2.json").write_text(
    json.dumps(data, indent=2) + "\n", encoding="utf-8"
)
print(f"Validated {len(ITEMS)} items and {len(QUESTIONS)} questions")
