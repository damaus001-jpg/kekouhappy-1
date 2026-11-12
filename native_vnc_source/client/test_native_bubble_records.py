import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from native_bubble_records import parse_bubble_records,date_separator

CONTACT='+12025550123'


def row(caption,identity):
    return {'caption':caption,'platform_identifier':identity}


class BubbleTests(unittest.TestCase):
    def test_recycled_id_does_not_replace_an_earlier_message(self):
        records=[row('Your Message, first, 14:04','reused'),
                 row('Your Message, second, 15:27','reused')]
        messages,_=parse_bubble_records(records,CONTACT)
        self.assertEqual([m['text'] for m in messages],['first','second'])
        self.assertEqual([m['time'] for m in messages],['14:04','15:27'])

    def test_identical_real_messages_on_distinct_nodes_remain_distinct(self):
        messages,_=parse_bubble_records([row('Your Message, same, 14:04','a'),
                                       row('Your Message, same, 14:04','b')],CONTACT)
        self.assertEqual(len(messages),2)

    def test_date_separator_applies_forward_without_guessing_year(self):
        records=[row('Your Message, before, 09:00','a'),row('Mon, Oct 12 at 13:04','date1'),
                 row('Your Message, one, 14:04','b'),row('Tue, Oct 13 at 13:04','date2'),
                 row('Your Message, two, 14:04','c')]
        messages,_=parse_bubble_records(records,CONTACT)
        self.assertIsNone(messages[0]['date'])
        self.assertEqual([m['date'] for m in messages[1:]],['10-12','10-13'])
        self.assertIsNone(messages[1]['date_year'])

    def test_picture_without_timestamp_is_preserved_and_followed_by_text(self):
        messages,_=parse_bubble_records([row('Mon, Oct 12 at 13:04','d'),
            row(CONTACT+', Includes picture','photo'),row('Your Message, next, 14:04','text')],CONTACT)
        self.assertEqual([m['kind'] for m in messages],['attachment','text'])
        self.assertEqual(messages[0]['date'],'10-12')

    def test_explicit_year_is_preserved_and_relative_label_is_not_guessed(self):
        self.assertEqual(date_separator('2025年10月12日 13:04')['date'],'2025-10-12')
        self.assertEqual(date_separator('Yesterday at 13:04')['date_label'],'Yesterday at 13:04')
        self.assertIsNone(date_separator('Yesterday at 13:04')['date'])
        self.assertIsNone(date_separator('Oct 99 at 13:04'))


if __name__=='__main__':
    unittest.main()
