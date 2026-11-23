from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import native_workspace as native
from native_conversation import phone_key


def rows(*captions):
    return [{'caption': c} for c in captions]


class ComposeRecipientFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_enters_precede_any_body_verification_even_if_imessage_body_is_late(self):
        number = '+19095834044'
        pages = [rows('New Message, Show Conversation Details, Button', 'To:', 'Message'),
                 rows('To:, ' + number),
                 rows('New iMessage, Show Conversation Details, Button', 'To:, \ufffc', number + ', Button'),
                 rows('New iMessage, Show Conversation Details, Button', 'To:, \ufffc', number + ', Button', 'Message, iMessage')]
        events = []
        async def read(_):
            events.append('read')
            return pages.pop(0)
        async def key(usages):
            events.append(('keys', usages))
        phone = SimpleNamespace(chord=AsyncMock(), paste=AsyncMock(), keys=AsyncMock(side_effect=key))
        with patch.object(native, 'list_page', new=AsyncMock()), \
                patch.object(native, 'raw_page', new=AsyncMock(side_effect=read)), \
                patch.object(native.asyncio, 'sleep', new=AsyncMock()):
            result = await native.enter_compose_recipient(None, phone, number, verify_selection=True)
        self.assertEqual(events, ['read', 'read', ('keys', [0x28]), ('keys', []),
                                  ('keys', [0x28]), ('keys', []), 'read', 'read'])
        self.assertTrue(native.composer_is_empty([r['caption'] for r in result]))
        phone.paste.assert_awaited_once_with(number)

    async def test_delayed_number_observation_retries_reading_not_pasting_or_enters(self):
        number = '+16189175409'
        pages = [rows('New Message, Show Conversation Details, Button', 'To:', 'Message'),
                 rows('To:'), rows('To:, \u200e' + number), rows(number + ', Button', 'Message')]
        phone = SimpleNamespace(chord=AsyncMock(), paste=AsyncMock(), keys=AsyncMock())
        progress = []
        with patch.object(native, 'list_page', new=AsyncMock()), \
                patch.object(native, 'raw_page', new=AsyncMock(side_effect=pages)), \
                patch.object(native.asyncio, 'sleep', new=AsyncMock()):
            await native.enter_compose_recipient(None, phone, number, verify_selection=True,
                progress=lambda stage, evidence: progress.append((stage, evidence)))
        phone.paste.assert_awaited_once_with(number)
        self.assertEqual([call.args[0] for call in phone.keys.await_args_list], [[0x28], [], [0x28], []])
        self.assertEqual([e['attempt'] for stage, e in progress if stage == 'recipient_input'], [1, 2])

    async def test_real_body_draft_after_enters_is_preserved_and_not_replaced(self):
        number = '+17249319521'
        draft = rows(number + ', Button', 'Message, actual draft', 'Send, Button')
        pages = [rows('New Message, Show Conversation Details, Button', 'To:', 'Message'),
                 rows('To:, ' + number), *[draft] * 4]
        phone = SimpleNamespace(chord=AsyncMock(), paste=AsyncMock(), keys=AsyncMock())
        with patch.object(native, 'list_page', new=AsyncMock()), \
                patch.object(native, 'raw_page', new=AsyncMock(side_effect=pages)), \
                patch.object(native.asyncio, 'sleep', new=AsyncMock()):
            with self.assertRaisesRegex(ValueError, '正文'):
                await native.enter_compose_recipient(None, phone, number, verify_selection=True)
        phone.paste.assert_awaited_once_with(number)

    def test_direction_markers_and_multiple_recipient_chips(self):
        self.assertEqual(phone_key('\u200e+1 (909) 583-4044'), '+19095834044')
        self.assertTrue(native.typed_recipient_confirmed(rows('To:, To:\ufffc+1 (909) 583-4044'), '+19095834044'))
        self.assertFalse(native.task_recipient_confirmed(rows('+19095834044, Button', '+17249319521, Button'), '+19095834044'))
        self.assertTrue(native.task_recipient_confirmed(rows('To:, \ufffc', '+19095834044, Button',
            'Add Contact, Button', '+17249319521, Button', 'Message'), '+19095834044'))


if __name__ == '__main__':
    unittest.main()
