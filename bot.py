from collections import defaultdict
from decimal import Decimal

from pydantic import BaseModel
from ape import project
from ape_ethereum import multicall
from ape_tokens import Token
from silverback import SilverbackBot
from datetime import datetime


class Deposit(BaseModel):
    time: datetime = datetime.now()
    price: Decimal


bot = SilverbackBot()


@bot.on_startup()
async def load_users(_):
    bot.state.vaults = defaultdict(list)
    bot.state.users = defaultdict(dict)


@bot.on_(project.ERC4626.Deposit)
async def deposit(log):
    vault = project.ERC4626.at(log.contract_address)
    try:
        token = Token.at(vault.asset())
    except AttributeError:
        print(f"Vault '{vault}' does not implement ERC4626!")
        return  # NOTE: Not implementing the full spec!

    if vault not in bot.state.vaults[token]:
        bot.state.vaults[token].append(vault)

    deposit_price = Decimal(log.assets) / Decimal(log.shares)
    bot.state.users[vault][log.owner] = Deposit(price=deposit_price)


@bot.on_(project.ERC4626.Withdraw)
async def withdraw(log):
    vault = project.ERC4626.at(log.contract_address)
    try:
        token = Token.at(vault.asset())
    except AttributeError:
        print(f"Vault '{vault}' does not implement ERC4626!")
        return  # NOTE: Not implementing the full spec!

    if vault not in bot.state.vaults[token]:
        bot.state.vaults[token].append(vault)

    current_price = Decimal(log.assets) / Decimal(log.shares)
    if deposit := bot.state.users[vault].pop(log.owner, None):
        rate_of_return = (
            (current_price - deposit.price)
            / Decimal((datetime.now() - deposit.time).total_seconds())
        ) * 365 * 24 * 60 * 60
        return {f"{token.symbol()} [{vault.address}]": rate_of_return}


@bot.cron("* * * * *")
async def total_tracking(_):
    total_tracking_per_token: dict[str, int] = dict()
    for token, vaults in bot.state.vaults.items():
        call = multicall.Call()
        for vault in vaults:
            call.add(vault.totalAssets)
        total_tracking_per_token[token.symbol()] = (
            sum(call()) / 10 ** token.decimals()
        )

    return total_tracking_per_token
