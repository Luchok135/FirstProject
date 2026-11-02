import tempfile
import unittest
from betbot.store import Store, PERIOD

class SubscriptionTests(unittest.TestCase):
    def test_payment_retry_does_not_extend_subscription(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(d+'/db')
            self.assertTrue(s.grant(7,'payment',100))
            self.assertFalse(s.grant(7,'payment',200))
            self.assertEqual(s.db.execute('SELECT until FROM subscriptions').fetchone()[0],100+PERIOD)

    def test_renewal_preserves_remaining_time(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(d+'/db')
            s.grant(7,'first',100)
            s.grant(7,'second',200)
            self.assertEqual(s.db.execute('SELECT until FROM subscriptions').fetchone()[0],100+2*PERIOD)

    def test_expired_subscription_starts_from_payment(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(d+'/db')
            s.grant(7,'first',100)
            s.grant(7,'second',100+PERIOD+20)
            self.assertEqual(s.db.execute('SELECT until FROM subscriptions').fetchone()[0],100+2*PERIOD+20)
