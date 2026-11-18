import unittest
from netpulse.monitor import classify_link_health


class NetPulseTests(unittest.TestCase):
    def test_link_health_classification(self):
        self.assertEqual(classify_link_health(0.15, 0), "LOW_LATENCY_OPTIMAL")
        self.assertEqual(classify_link_health(1.2, 0), "ELEVATED_RETRANS")
        self.assertEqual(classify_link_health(3.1, 0), "CONGESTED")
        self.assertEqual(classify_link_health(0.1, 250), "CONGESTED")


if __name__ == "__main__":
    unittest.main()
