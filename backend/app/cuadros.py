"""Construye cuadros, sin consultar ni guardar en la base de datos."""
from math import ceil


def next_power(number):
    return 1 << (number - 1).bit_length()


def seed_order(size):
    order = [1, 2]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [seed for old in order for seed in (old, total - old)]
    return order


def entry(participant_id):
    return {'participant_id': participant_id}


def source(match_key, outcome='winner'):
    return {'source_match': match_key, 'outcome': outcome}


def stage(plan, key, kind, name):
    value = {'key': key, 'kind': kind, 'name': name, 'position': len(plan['stages']) + 1, 'rounds': []}
    plan['stages'].append(value)
    return value


def round_matches(stage_data, slots, title=None):
    number = len(stage_data['rounds']) + 1
    matches = []
    for index in range(0, len(slots), 2):
        position = index // 2 + 1
        matches.append({'key': f"{stage_data['key']}-{number}-{position}",
                        'position': position, 'slots': slots[index:index + 2]})
    stage_data['rounds'].append({'number': number, 'name': title or f'Ronda {number}', 'matches': matches})
    return [match['key'] for match in matches]


def knockout(plan, key, kind, name, competitors, first_slots=None):
    bracket = stage(plan, key, kind, name)
    size = next_power(len(competitors))
    slots = first_slots if first_slots is not None else [competitors[seed - 1] if seed <= len(competitors) else {} for seed in seed_order(size)]
    rounds = []
    while len(slots) >= 2:
        count = len(slots) // 2
        title = 'Final' if count == 1 else 'Semifinales' if count == 2 else f'Ronda de {len(slots)}'
        matches = round_matches(bracket, slots, title)
        rounds.append(matches)
        slots = [source(match) for match in matches]
    return rounds


def double_elimination(plan, participant_ids):
    upper = knockout(plan, 'U', 'upper', 'Upper bracket', [entry(pid) for pid in participant_ids])
    lower = stage(plan, 'L', 'lower', 'Lower bracket')
    if len(upper) == 1:
        # Con dos jugadores, el perdedor del upper ya es el finalista del lower.
        lower_finalist = source(upper[0][0], 'loser')
    else:
        current = round_matches(lower, [source(key, 'loser') for key in upper[0]])
        for upper_number in range(1, len(upper)):
            incoming = list(reversed(upper[upper_number]))
            slots = []
            for previous, upper_match in zip(current, incoming):
                slots.extend([source(previous), source(upper_match, 'loser')])
            last = upper_number == len(upper) - 1
            current = round_matches(lower, slots, 'Final del lower' if last else None)
            if not last:
                current = round_matches(lower, [source(key) for key in current])
        lower_finalist = source(current[0])
    final = stage(plan, 'F', 'final', 'Final general')
    round_matches(final, [source(upper[-1][0]), lower_finalist], 'Final general')


def group_schedule(stage_data, participant_ids):
    # Método del círculo: todos contra todos a una vuelta, sin repetir parejas.
    players = list(participant_ids)
    if len(players) % 2:
        players.append(None)
    for _ in range(len(players) - 1):
        slots = []
        for index in range(len(players) // 2):
            first, second = players[index], players[-index - 1]
            if first is not None and second is not None:
                slots.extend([entry(first), entry(second)])
        round_matches(stage_data, slots, f'Jornada {len(stage_data["rounds"]) + 1}')
        players = [players[0], players[-1], *players[1:-1]]


def groups_knockout(plan, participant_ids):
    count = ceil(len(participant_ids) / 4)
    groups = [[] for _ in range(count)]
    for index, participant_id in enumerate(participant_ids):
        groups[index % count].append(participant_id)
    for index, members in enumerate(groups):
        key = f'G{index + 1}'
        label = chr(65 + index) if index < 26 else 'A' + chr(65 + index - 26)
        group = stage(plan, key, 'group', f'Grupo {label}')
        plan['groups'].append({'stage_key': key, 'participant_ids': members})
        group_schedule(group, members)
    winners = [{'source_group': f'G{index + 1}', 'rank': 1} for index in range(count)]
    runners = [{'source_group': f'G{index + 1}', 'rank': 2} for index in range(count)]
    byes = next_power(2 * count) - 2 * count
    slots = []
    if byes <= count:
        for index in range(count):
            slots.extend([winners[index], {} if index < byes else runners[(index + 1) % count]])
        remaining = [runners[(index + 1) % count] for index in range(byes)]
    else:
        for winner in winners:
            slots.extend([winner, {}])
        extra = byes - count
        for runner in runners[:extra]:
            slots.extend([runner, {}])
        remaining = runners[extra:]
    slots.extend(remaining)
    knockout(plan, 'K', 'knockout', 'K.O. después de grupos', winners + runners, slots)


def league(plan, participant_ids, turns):
    table=stage(plan,'C','league','Liga')
    plan['groups'].append({'stage_key':'C','participant_ids':list(participant_ids)})
    group_schedule(table,participant_ids)
    # Alternar local/visitante en la ida. La vuelta invierte cada partido.
    for index,round_data in enumerate(table['rounds']):
        for position,game in enumerate(round_data['matches']):
            if (index+position)%2: game['slots'].reverse()
    if turns==2:
        calendar=[r['matches'] for r in table['rounds']]
        for games in calendar:
            slots=[slot for game in games for slot in reversed(game['slots'])]
            round_matches(table,slots,f'Jornada {len(table["rounds"])+1} · vuelta')


def generate(format_name, participant_ids, league_rounds=1):
    plan = {'stages': [], 'groups': [], 'entry_order': list(participant_ids)}
    if format_name == 'single_elimination':
        knockout(plan, 'K', 'knockout', 'Eliminación directa', [entry(pid) for pid in participant_ids])
    elif format_name == 'double_elimination':
        double_elimination(plan, participant_ids)
    elif format_name == 'league':
        league(plan,participant_ids,league_rounds)
    elif format_name == 'groups_knockout':
        groups_knockout(plan, participant_ids)
    else:
        raise ValueError('Formato desconocido')
    return plan
