"""Behavioral regressions for crew dependency, branching and training profiles."""
import copy
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location('carbon_contract_tests', Path(__file__).with_name('test_last_carbon_isles.py'))
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def public_plans(public, *, forbid_training=False):
    """Enumerate allocation routes from public policy/region data, no witness IDs."""
    regions = public['regions']
    indexes = {r['id']: i for i, r in enumerate(regions)}
    cards = public['cards']
    budget = public['budget'] - sum(t['cost'] for t in public['research_tracks'])
    solutions = []
    dead_ends = []

    def search(jobs, cleared, remaining, path):
        if len(cleared) == len(regions):
            solutions.append(path)
            return
        legal = []
        for card in cards:
            target = indexes[card['home_region']]
            if target in cleared or card['cost'] > remaining:
                continue
            if forbid_training and card['title'] == 'Training retrofit':
                continue
            if any(indexes[q['region_id']] not in cleared or jobs[indexes[q['region_id']]] < q['jobs'] for q in card['requirements']):
                continue
            legal.append(card)
        if not legal:
            dead_ends.append(path)
        for card in legal:
            after = list(jobs)
            target = indexes[card['home_region']]
            after[target] += card['target_effect']['jobs']
            for donor, effect in card['side_effects'].items():
                after[indexes[donor]] += effect['jobs']
            search(after, cleared | {target}, remaining - card['cost'], path + [card['id']])

    search([r['jobs'] for r in regions], set(), budget, [])
    return solutions, dead_ends


def test_upper_profiles_have_required_order_branching_and_training():
    for seed in range(20):
        for level in (3, 4, 5):
            public, truth = contract.GENERATOR.generate(contract._task(level, 'full'), f'network-test-{seed}')
            solutions, dead_ends = public_plans(public)
            assert solutions, (level, seed)
            if level == 3:
                assert len(solutions) == 1
            if level == 4:
                assert dead_ends, 'branch choices must have a possible dead end'
            if level == 5:
                untrained, _ = public_plans(public, forbid_training=True)
                assert not untrained, 'an all-cheap/all-positive cue route must not bypass training'
            assert all(c['target_effect']['jobs'] > 0 for c in public['cards'])
            assert all(len({c['accent'] for c in t['offers']}) == 1 for t in public['research_tracks'])
            payload = {'mechanic_id': 'last_carbon_isles', 'task_id': truth['task_id'],
                       'challenge_id': truth['challenge_id'],
                       'events': contract._solution_events(public, truth, 'full')}
            assert contract.GRADER.grade(payload, truth, public)['passed']
            alternative = copy.deepcopy(truth)
            alternative['witness_route'] = solutions[0]
            public_plan_payload = {**payload, 'events': contract._solution_events(public, alternative, 'full')}
            assert contract.GRADER.grade(public_plan_payload, truth, public)['passed']
            broken = copy.deepcopy(payload)
            plays = [i for i,e in enumerate(broken['events']) if e['kind'] == 'play']
            a,b = plays[:2]
            first,second = broken['events'][a],broken['events'][b]
            for key in ('card_id','region_id','cost'):
                first[key],second[key] = second[key],first[key]
            assert not contract.GRADER.grade(broken, truth, public)['passed']


def test_original_world_matches_saved_pre_network_baseline():
    import json
    import hashlib
    # Frozen from the pre-network audit's d2 live export, including its runtime seed suffix.
    generated, _ = contract.GENERATOR.generate(contract._task(2, 'full'), 'last-carbon-browser-d2:refresh:1')
    for key in ('task_id', 'challenge_id', 'control_condition', 'prompt'):
        generated.pop(key, None)
    digest = hashlib.sha256(json.dumps(generated, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert digest == 'd7075af509674f45a984b4dafe69f413d8b691256b2b4305ac2339af26b4756a'
