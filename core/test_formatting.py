
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.formatting import (
    DEFAULT_TIMEZONE, format_date, format_datetime, format_money, format_time,
    group_indian, tenant_timezone, to_local,
)


class _Tenant:
    def __init__(self, tz):
        self.timezone = tz


class MoneyTests(SimpleTestCase):
    def test_the_locked_examples(self):
        self.assertEqual(format_money(Decimal('49875.00')), '₹49,875')
        self.assertEqual(format_money(Decimal('100000')), '₹1,00,000')
        self.assertEqual(format_money(Decimal('1234567')), '₹12,34,567')
        self.assertEqual(format_money(Decimal('49875.50')), '₹49,875.50')

    def test_paise_appear_only_when_there_are_paise(self):
        self.assertEqual(format_money(Decimal('100.00')), '₹100')
        self.assertEqual(format_money(Decimal('100.05')), '₹100.05')
        self.assertEqual(format_money(Decimal('100.50')), '₹100.50')

    def test_lakh_grouping_not_western(self):
        self.assertEqual(group_indian('100000'), '1,00,000')
        self.assertEqual(group_indian('999'), '999')
        self.assertEqual(group_indian('1000'), '1,000')
        self.assertEqual(group_indian('12345678'), '1,23,45,678')

    def test_junk_does_not_raise_on_a_customer_facing_page(self):
        for value in (None, '', 'abc', []):
            self.assertEqual(format_money(value), '₹0')

    def test_negatives_keep_their_sign_outside_the_symbol(self):
        self.assertEqual(format_money(Decimal('-2500')), '-₹2,500')

    def test_a_float_total_formats_the_same_as_its_decimal(self):
        self.assertEqual(format_money(49875.0), format_money(Decimal('49875.00')))


class TimezoneTests(SimpleTestCase):
    UTC_INSTANT = datetime(2026, 8, 24, 9, 30, 17, tzinfo=dt_timezone.utc)

    def test_a_stored_utc_instant_renders_in_the_boutiques_time(self):
        tenant = _Tenant('Asia/Kolkata')
        self.assertEqual(format_time(self.UTC_INSTANT, tenant), '3:00 PM')
        self.assertEqual(format_datetime(self.UTC_INSTANT, tenant),
                         '24 Aug 2026, 3:00 PM')

    def test_a_different_boutique_reads_a_different_clock(self):
        self.assertEqual(format_time(self.UTC_INSTANT, _Tenant('Asia/Dubai')), '1:30 PM')
        self.assertEqual(format_time(self.UTC_INSTANT, _Tenant('UTC')), '9:30 AM')

    def test_conversion_never_touches_the_stored_value(self):
        local = to_local(self.UTC_INSTANT, _Tenant('Asia/Kolkata'))
        self.assertEqual(local.astimezone(dt_timezone.utc), self.UTC_INSTANT,
                         'the instant is the same; only its wall clock differs')
        self.assertEqual(self.UTC_INSTANT.tzinfo, dt_timezone.utc,
                         'the original is unmodified')

    def test_a_date_crossing_midnight_moves_with_the_clock(self):
        late = datetime(2026, 8, 24, 20, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(format_date(late, _Tenant('Asia/Kolkata')), '25 Aug 2026')
        self.assertEqual(format_date(late, _Tenant('UTC')), '24 Aug 2026')

    def test_a_broken_timezone_name_falls_back_rather_than_erroring(self):
        self.assertEqual(tenant_timezone(_Tenant('Not/AZone')),
                         ZoneInfo(DEFAULT_TIMEZONE))

    def test_a_tenant_with_no_timezone_uses_the_default(self):
        self.assertEqual(tenant_timezone(_Tenant('')), ZoneInfo(DEFAULT_TIMEZONE))

    def test_a_naive_datetime_is_read_as_utc(self):
        naive = datetime(2026, 8, 24, 9, 30)
        self.assertEqual(format_time(naive, _Tenant('Asia/Kolkata')), '3:00 PM')

    def test_none_renders_blank_rather_than_the_word_none(self):
        self.assertEqual(format_date(None), '')
        self.assertEqual(format_time(None), '')
        self.assertEqual(format_datetime(None), '')


class DateFormatTests(SimpleTestCase):
    def test_the_locked_shapes(self):
        instant = datetime(2026, 8, 4, 9, 30, tzinfo=dt_timezone.utc)
        tenant = _Tenant('Asia/Kolkata')
        self.assertEqual(format_date(instant, tenant), '4 Aug 2026')
        self.assertEqual(format_time(instant, tenant), '3:00 PM')
