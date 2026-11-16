import unittest
from unittest.mock import Mock
from cpu_metrics import WindowsCpuUtility


class WindowsCpuUtilityTests(unittest.TestCase):
    def counter(self):
        library = Mock()
        for name in ('PdhOpenQueryW', 'PdhAddEnglishCounterW', 'PdhCollectQueryData',
                     'PdhGetFormattedCounterValue', 'PdhCloseQuery'):
            getattr(library, name).return_value = 0
        def open_query(source, data, output):
            output._obj.value = 123
            return 0
        library.PdhOpenQueryW.side_effect = open_query
        return WindowsCpuUtility(library), library

    def test_reads_total_utility_after_baseline_and_caps_percentage(self):
        counter, library = self.counter()
        self.assertEqual(counter(), 0)
        library.PdhGetFormattedCounterValue.assert_not_called()
        self.assertEqual(library.PdhAddEnglishCounterW.call_args.args[1],
                         r'\Processor Information(_Total)\% Processor Utility')
        def formatted(handle, flags, counter_type, output):
            output._obj.status = 0
            output._obj.value = 135.5
            return 0
        library.PdhGetFormattedCounterValue.side_effect = formatted
        self.assertEqual(counter(), 100)
        counter.close()
        counter.close()
        library.PdhCloseQuery.assert_called_once()

    def test_invalid_counter_data_clears_query_and_rewarms(self):
        counter, library = self.counter()
        counter()
        def invalid(handle, flags, counter_type, output):
            output._obj.status = 0xC0000BC6
            return 0
        library.PdhGetFormattedCounterValue.side_effect = invalid
        with self.assertRaises(OSError):
            counter()
        self.assertIsNone(counter.query.value)
        self.assertFalse(counter.primed)
        library.PdhCloseQuery.assert_called_once()
        self.assertEqual(counter(), 0)
        self.assertEqual(library.PdhOpenQueryW.call_count, 2)
        counter.close()

    def test_missing_counter_closes_allocated_query(self):
        counter, library = self.counter()
        library.PdhAddEnglishCounterW.return_value = 0xC0000BB8
        with self.assertRaises(OSError):
            counter()
        library.PdhCloseQuery.assert_called_once()


if __name__ == '__main__':
    unittest.main()
