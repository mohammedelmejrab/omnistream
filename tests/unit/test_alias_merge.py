"""Unit tests for the alias-merge dry-run planner (against a fake store)."""

from omnistream.eval.diagnostics.alias_merge import (
    EntityRec,
    EpisodeRec,
    GlobalRec,
    MergePlan,
    plan_alias_merges,
)


def test_split_pair_plans_merge():
    episodes = [
        EpisodeRec(
            "ep1",
            "g",
            "AVT, the listed abbreviation used by Aldervane Transit, signed.",
            "item1",
        )
    ]
    entities = [
        EntityRec("e-full", "Aldervane Transit", "Organization", "g-full"),
        EntityRec("e-short", "AVT", "Organization", "g-short"),
    ]
    globals = [
        GlobalRec("g-full", "Aldervane Transit", "Organization"),
        GlobalRec("g-short", "AVT", "Organization"),
    ]
    plan = plan_alias_merges(episodes, entities, globals)
    assert len(plan.merges()) == 1
    m = plan.merges()[0]
    assert (m.full, m.short) == ("Aldervane Transit", "AVT")
    assert m.full_global == "g-full" and m.short_global == "g-short"
    assert m.same_as_edges_changed == 1


def test_already_merged_no_action():
    episodes = [
        EpisodeRec("ep1", "g", "Cobalt Reach Laboratory (CRL) reported.", "item1")
    ]
    entities = [
        EntityRec("e-full", "Cobalt Reach Laboratory", "Organization", "g1"),
        EntityRec("e-short", "CRL", "Organization", "g1"),
    ]
    globals = [GlobalRec("g1", "Cobalt Reach Laboratory", "Organization", ["CRL"])]
    plan = plan_alias_merges(episodes, entities, globals)
    assert plan.merges() == []
    assert [p.decision for p in plan.pairs] == ["already_merged"]


def test_missing_side():
    episodes = [
        EpisodeRec("ep1", "g", "AVT, the listed abbreviation used by Aldervane Transit.", "i1")
    ]
    entities = [EntityRec("e-short", "AVT", "Organization", "g-short")]
    globals = [GlobalRec("g-short", "AVT", "Organization")]
    plan = plan_alias_merges(episodes, entities, globals)
    assert [p.decision for p in plan.pairs] == ["missing_side"]


def test_number_token_refused():
    episodes = [
        EpisodeRec(
            "ep1", "g", "Dovetail Quay 10, formerly Dovetail Quay 9.", "i1"
        )
    ]
    entities = [
        EntityRec("e10", "Dovetail Quay 10", "Organization", "g10"),
        EntityRec("e9", "Dovetail Quay 9", "Organization", "g9"),
    ]
    globals = [
        GlobalRec("g10", "Dovetail Quay 10", "Organization"),
        GlobalRec("g9", "Dovetail Quay 9", "Organization"),
    ]
    plan = plan_alias_merges(episodes, entities, globals)
    assert [p.decision for p in plan.pairs] == ["refused_number_token"]


def test_type_conflict_refused():
    episodes = [
        EpisodeRec(
            "ep1", "g", "HVM, the listed abbreviation used by Halvex Mobility.", "i1"
        )
    ]
    entities = [
        EntityRec("e-full", "Halvex Mobility", "Organization", "g-full"),
        EntityRec("e-short", "HVM", "Product", "g-short"),
    ]
    globals = [
        GlobalRec("g-full", "Halvex Mobility", "Organization"),
        GlobalRec("g-short", "HVM", "Product"),
    ]
    plan = plan_alias_merges(episodes, entities, globals)
    assert [p.decision for p in plan.pairs] == ["refused_type_conflict"]


def test_ambiguity_refused():
    episodes = [
        EpisodeRec("ep1", "g", "AVT, the listed abbreviation used by Aldervane Transit.", "i1"),
        EpisodeRec("ep2", "g", "AVT, the listed abbreviation used by Aldervain Travel.", "i2"),
    ]
    entities = [
        EntityRec("e1", "Aldervane Transit", "Organization", "g1"),
        EntityRec("e2", "Aldervain Travel", "Organization", "g2"),
        EntityRec("e3", "AVT", "Organization", "g3"),
    ]
    globals = [
        GlobalRec("g1", "Aldervane Transit", "Organization"),
        GlobalRec("g2", "Aldervain Travel", "Organization"),
        GlobalRec("g3", "AVT", "Organization"),
    ]
    plan = plan_alias_merges(episodes, entities, globals)
    assert all(p.decision == "refused_ambiguity" for p in plan.pairs)


def test_eval_v2_style_finds_all_pairs():
    companies = [
        ("Halvex Mobility", "HVM"),
        ("Nacreline Systems", "NLS"),
        ("Brindle Arc", "BDA"),
        ("Oxbriar Robotics", "OBR"),
        ("Vespergate Works", "VGW"),
        ("Quenara Devices", "QND"),
        ("Tesselmere Controls", "TMC"),
        ("Aldervane Transit", "AVT"),
        ("Pellucid Forge", "PCF"),
        ("Ravenspire Instruments", "RSI"),
    ]
    labs = [
        ("Cobalt Reach Laboratory", "CRL"),
        ("Juniper Basin Institute", "JBI"),
        ("Sable Meridian Centre", "SMC"),
        ("Ivory Delta Laboratory", "IDL"),
        ("Copper Fen Institute", "CFI"),
        ("Indigo Vale Centre", "IVC"),
        ("Opal Ridge Laboratory", "ORL"),
        ("Ochre Hollow Institute", "OHI"),
        ("Violet Strand Centre", "VSC"),
        ("Silver Marsh Laboratory", "SML"),
    ]
    episodes, entities, globals = [], [], []
    for i, (co, alias) in enumerate(companies):
        lab, short = labs[i]
        episodes.append(
            EpisodeRec(
                f"ep{i}",
                "g",
                f"ANALYST NOTE. {alias}, the listed abbreviation used by {co}, signed "
                f"a research funding agreement with {lab} ({short}) on February 7.",
                f"item{i}",
            )
        )
    for i, (co, alias) in enumerate(companies):
        entities.append(EntityRec(f"c{i}", co, "Organization", f"gc{i}"))
        entities.append(EntityRec(f"a{i}", alias, "Organization", f"ga{i}"))
        globals.append(GlobalRec(f"gc{i}", co, "Organization"))
        globals.append(GlobalRec(f"ga{i}", alias, "Organization"))
    for i, (lab, short) in enumerate(labs):
        entities.append(EntityRec(f"l{i}", lab, "Organization", f"gl{i}"))
        entities.append(EntityRec(f"s{i}", short, "Organization", f"gs{i}"))
        globals.append(GlobalRec(f"gl{i}", lab, "Organization"))
        globals.append(GlobalRec(f"gs{i}", short, "Organization"))

    plan = plan_alias_merges(episodes, entities, globals)
    assert plan.summary()["pairs_found"] == 20
    assert plan.summary()["merges"] == 20
    assert plan.summary()["same_as_edges_to_change"] == 20
    assert plan.summary()["refused_number_token"] == 0
    assert plan.summary()["refused_type_conflict"] == 0
    assert plan.summary()["refused_ambiguity"] == 0


def test_summary_counts_each_decision_once():
    plan = MergePlan(groups=["g"])
    assert set(plan.summary()) >= {
        "pairs_found",
        "merges",
        "same_as_edges_to_change",
        "already_merged",
        "missing_side",
        "refused_type_conflict",
        "refused_number_token",
        "refused_ambiguity",
    }
