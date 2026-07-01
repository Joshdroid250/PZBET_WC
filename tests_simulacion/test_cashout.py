import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs import betting_cog


class TestCashoutSelect(unittest.IsolatedAsyncioTestCase):
    def make_interaction(self, user_id=123):
        interaction = MagicMock()
        interaction.user.id = user_id
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.message.edit = AsyncMock()
        return interaction

    def make_select(self):
        bot = MagicMock()
        bot.session = AsyncMock()
        return betting_cog.CashoutSelect(
            [("Mexico", "Korea Republic", 10.0, "HOME_TEAM", "400021442")],
            is_parlay=False,
            user_id=123,
            bot=bot,
        )

    async def test_cashout_minute_90_sends_lock_after_defer(self):
        select = self.make_select()
        interaction = self.make_interaction()

        with patch.object(betting_cog.CashoutSelect, "values", new_callable=PropertyMock) as values:
            values.return_value = ["ind_400021442_10.0"]
            with patch.object(betting_cog.api_football, "get_match_details", new=AsyncMock(return_value={
                "status": "IN_PLAY",
                "utcDate": "2026-06-19T01:00:00Z",
            })):
                with patch.object(betting_cog.api_football, "calculate_match_minute", return_value=90.0):
                    with patch.object(betting_cog.database, "remove_bet", new=AsyncMock()) as remove_bet:
                        with patch.object(betting_cog.database, "update_balance", new=AsyncMock()) as update_balance:
                            await select.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("Mercado Suspendido", message)
        remove_bet.assert_not_awaited()
        update_balance.assert_not_awaited()

    async def test_cashout_missing_match_info_sends_controlled_error(self):
        select = self.make_select()
        interaction = self.make_interaction()

        with patch.object(betting_cog.CashoutSelect, "values", new_callable=PropertyMock) as values:
            values.return_value = ["ind_400021442_10.0"]
            with patch.object(betting_cog.api_football, "get_match_details", new=AsyncMock(return_value=None)):
                with patch.object(betting_cog.database, "remove_bet", new=AsyncMock()) as remove_bet:
                    await select.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("No se pudo verificar", message)
        remove_bet.assert_not_awaited()

    async def test_cashout_missing_utc_date_sends_controlled_error(self):
        select = self.make_select()
        interaction = self.make_interaction()

        with patch.object(betting_cog.CashoutSelect, "values", new_callable=PropertyMock) as values:
            values.return_value = ["ind_400021442_10.0"]
            with patch.object(betting_cog.api_football, "get_match_details", new=AsyncMock(return_value={
                "status": "IN_PLAY",
            })):
                with patch.object(betting_cog.database, "remove_bet", new=AsyncMock()) as remove_bet:
                    await select.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("No se pudo calcular", message)
        remove_bet.assert_not_awaited()

    async def test_cashout_does_not_credit_when_bet_was_not_removed(self):
        select = self.make_select()
        interaction = self.make_interaction()

        with patch.object(betting_cog.CashoutSelect, "values", new_callable=PropertyMock) as values:
            values.return_value = ["ind_55_400021442_10.0"]
            with patch.object(betting_cog.api_football, "get_match_details", new=AsyncMock(return_value={
                "status": "IN_PLAY",
                "utcDate": "2026-06-19T01:00:00Z",
            })):
                with patch.object(betting_cog.api_football, "calculate_match_minute", return_value=45.0):
                    with patch.object(betting_cog.database, "remove_bet_by_id", new=AsyncMock(return_value=0)):
                        with patch.object(betting_cog.database, "update_balance", new=AsyncMock()) as update_balance:
                            await select.callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("No se encontr", message)
        update_balance.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
