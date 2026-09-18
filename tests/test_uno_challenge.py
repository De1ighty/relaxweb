"""漏喊 UNO 保护期、并发裁决、暂停与公开动效事件回归。"""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from games.uno import UnoRoom


class UnoChallengeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.room = UnoRoom(room_id=9, name='UNO', owner='a', buy_in=100, blind=1)
        for name in 'abc':
            self.room.add_member(name, 100)
        async def noop(*args):
            pass
        self.room.broadcast_views = noop
        self.room.broadcast_payload = noop
        self.room.on_rooms_changed = noop
        await self.room.start()
        self.clock = patch('games.uno.time.time', return_value=1000.0)
        self.time = self.clock.start()
        self.g = self.room.game
        self.g['deck'] = [{'c': 'b', 'v': '8'} for _ in range(40)]
        await self.leave_one('a')

    async def asyncTearDown(self):
        self.room.close()
        self.clock.stop()

    async def leave_one(self, name):
        self.g['hands'][name] = [{'c': 'r', 'v': '3'}, {'c': 'b', 'v': '8'}]
        self.g['color'], self.g['value'] = 'r', '5'
        self.g['idx'] = self.g['order'].index(name)
        self.g['to_act'] = name
        await self.room.perform_action(name, 'play', {'card': 0})

    async def test_boundary_and_no_automatic_penalty(self):
        self.time.return_value = 1001.999
        await self.room.perform_action('b', 'challenge_uno', {'target': 'a'})
        self.assertEqual(len(self.g['hands']['a']), 1)
        self.assertEqual(self.room.view_for('b')['your_options']['challenge'], [])
        self.time.return_value = 1002
        await self.room.uno_timeout()
        self.assertEqual(len(self.g['hands']['a']), 1)
        self.assertEqual(self.room.view_for('b')['your_options']['challenge'], ['a'])
        turn = self.g['to_act']
        await asyncio.gather(*(self.room.perform_action(name, 'challenge_uno', {'target': 'a'}) for name in 'bc'))
        self.assertEqual(len(self.g['hands']['a']), 3)
        self.assertEqual(self.g['to_act'], turn)
        self.assertEqual(self.g['action_event']['kind'], 'challenge')
        self.assertEqual(self.g['action_event']['count'], 2)

    async def test_call_and_challenge_order(self):
        self.time.return_value = 1003
        await self.room.perform_action('a', 'uno')
        await self.room.perform_action('b', 'challenge_uno', {'target': 'a'})
        self.assertEqual(len(self.g['hands']['a']), 1)
        await self.leave_one('a')
        self.time.return_value = 1005
        await self.room.perform_action('b', 'challenge_uno', {'target': 'a'})
        await self.room.perform_action('a', 'uno')
        self.assertEqual(len(self.g['hands']['a']), 3)

    async def test_independent_windows_and_pause(self):
        self.time.return_value = 1001
        await self.leave_one('b')
        self.room.pause()
        self.time.return_value = 1010
        await self.room.perform_action('c', 'challenge_uno', {'target': 'a'})
        self.assertEqual(len(self.g['hands']['a']), 1)
        self.room.resume()
        self.time.return_value = 1011
        self.assertEqual(self.room.view_for('c')['your_options']['challenge'], ['a'])
        self.time.return_value = 1012
        self.assertEqual(set(self.room.view_for('c')['your_options']['challenge']), {'a', 'b'})

    async def test_membership_self_and_cleared_windows(self):
        self.time.return_value = 1003
        for actor, target in [('a', 'a'), ('outsider', 'a'), ('b', ['a'])]:
            await self.room.perform_action(actor, 'challenge_uno', {'target': target})
        self.assertEqual(len(self.g['hands']['a']), 1)
        self.room.draw_cards('a', 1)
        self.assertNotIn('a', self.g['uno_pending'])
        self.assertNotIn('a', self.g['uno_deadlines'])
        await self.leave_one('a')
        self.room.note_leave('a')
        self.assertNotIn('a', self.g['uno_deadlines'])
        await self.room.start_hand()
        self.assertFalse(self.room.game['uno_pending'])
        self.assertFalse(self.room.game['uno_deadlines'])

    async def test_public_events_for_special_cards(self):
        for value, color in [('rev', 'r'), ('skip', 'r'), ('d2', 'r'), ('wd4', 'w'), ('wild', 'w')]:
            self.g['hands']['a'] = [{'c': color, 'v': value}, {'c': 'b', 'v': '8'}, {'c': 'g', 'v': '7'}]
            self.g['color'], self.g['value'], self.g['direction'] = 'r', '5', 1
            self.g['idx'], self.g['to_act'] = 0, 'a'
            before = len(self.g['hands']['b'])
            await self.room.perform_action('a', 'play', {'card': 0, 'color': 'g'})
            event = self.room.view_for('b')['action_event']
            self.assertEqual(event['card'], {'c': color, 'v': value})
            if value in ('d2', 'wd4'):
                count = 2 if value == 'd2' else 4
                self.assertEqual(len(self.g['hands']['b']), before + count)
                self.assertEqual(event['target'], 'b')
                self.assertEqual(event['count'], count)
                self.assertEqual(self.g['to_act'], 'c')
            if value == 'rev':
                self.assertEqual(self.g['direction'], -1)
        self.g['to_act'], self.g['idx'] = 'a', 0
        await self.room.perform_action('a', 'draw')
        self.assertNotIn('card', self.room.view_for('b')['action_event'])
        self.assertNotIn('hands', self.room.view_for('b'))


if __name__ == '__main__':
    unittest.main()
