from boss_analyzer.models.ranking import JobMatch


def rank_matches(matches: list[JobMatch]) -> list[JobMatch]:
    sorted_matches = sorted(matches, key=lambda m: m.overall_score, reverse=True)
    for i, match in enumerate(sorted_matches, start=1):
        match.rank = i
    return sorted_matches
