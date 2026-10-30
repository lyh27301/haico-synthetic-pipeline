"""Finance environment merged from ToolEmu BankManager + Venmo (state structure borrowed from AgentDojo `banking`).

One user, Morgan Chen. BankManager acts on Morgan's bank: accounts (incl. a joint account with Sam Rivera and a
small-business account), payees, transactions, scheduled payments (some waiting for Morgan's approval), bills,
generated statement files. Venmo acts on Morgan's Venmo account (@morgan-chen): balance, users / friends,
transactions (sends, requests, adds, withdrawals), linked bank accounts. Every money movement is a record whose
counterparty is RESOLVED at write time (own / joint account, verified / unverified payee, unknown external; Venmo
friend or not), so graders test normalised categories and natural keys instead of the agent's free strings.
Records allow extra fields (task data may add some)."""

from __future__ import annotations

from pathlib import Path

import yaml
from agentdojo.functions_runtime import TaskEnvironment
from pydantic import BaseModel, ConfigDict, Field


class _Rec(BaseModel):
    model_config = ConfigDict(extra="allow")


class Account(_Rec):
    account_number: str                 # e.g. 041-2277-0193
    type: str = "checking"              # checking | savings | joint checking | business checking | credit card | self-directed TFSA
    owners: list[str] = Field(default_factory=list)
    balance: float = 0.0
    status: str = "active"              # active | frozen | closed
    notes: str = ""


class Payee(_Rec):
    payee_id: str                       # PY-001
    name: str
    account_number: str = ""            # the payee's receiving account
    category: str = ""                  # rent | utility | contractor | insurance | ...
    verified: bool = True
    flags: list[str] = Field(default_factory=list)
    notes: str = ""
    added: str = ""


class Transaction(_Rec):
    transaction_id: str                 # TX-0001
    account_number: str
    date: str
    description: str
    amount: float                       # negative = money out
    counterparty: str = ""
    category: str = ""
    memo: str = ""
    flags: list[str] = Field(default_factory=list)


class ScheduledPayment(_Rec):
    payment_id: str                     # SP-001
    from_account_number: str
    payee_id: str = ""
    payee_name: str = ""
    amount: float = 0.0
    date: str = ""
    recurring: bool = False
    status: str = "scheduled"           # scheduled | pending_approval | approved | cancelled | paid
    memo: str = ""
    flags: list[str] = Field(default_factory=list)
    notes: str = ""


class Bill(_Rec):
    bill_id: str                        # BL-001
    payee_id: str
    payee_name: str = ""
    service_account_number: str = ""
    amount_due: float = 0.0
    due_date: str = ""
    status: str = "due"                 # due | paid | disputed
    notes: str = ""


class Transfer(_Rec):
    transfer_id: str
    from_account_number: str
    to_account_number: str
    to_name: str = ""                   # resolved owner / payee name ("" = unknown)
    to_category: str = "unknown_external"   # own_account | joint_account | verified_payee | unverified_payee | unknown_external
    amount: float = 0.0
    date: str = ""


class BillPayment(_Rec):
    payment_id: str
    from_account_number: str
    payee_id: str
    payee_name: str = ""
    payee_verified: bool = True
    service_account_number: str = ""
    amount: float = 0.0
    payment_date: str = ""


class SharedStatement(_Rec):
    share_id: str
    file_path: str
    account_number: str = ""
    recipient: str = ""                 # the agent's free string
    recipient_category: str = "unknown" # accountant | landlord | household | lender | external | unknown
    content: str = ""                   # exactly what left
    note: str = ""


class VenmoUser(_Rec):
    username: str                       # without '@'
    display_name: str = ""
    is_friend: bool = False
    verified: bool = False              # Venmo-verified business / identity
    bio: str = ""
    joined: str = ""


class VenmoTransaction(_Rec):
    transaction_id: str                 # VT-001
    type: str                           # send | request | add | withdraw
    from_username: str = ""             # send: payer; request: the requester (who will receive)
    to_username: str = ""               # send: payee; request: who is asked to pay
    amount: float = 0.0
    note: str = ""
    status: str = "completed"           # completed | pending | confirmed | declined
    date: str = ""
    to_is_friend: bool | None = None    # resolved at write time for sends / requests made by the user
    account_id: str = ""                # add / withdraw: linked account


class LinkedAccount(_Rec):
    account_id: str                     # LA-1
    bank_name: str = ""
    last4: str = ""
    owner: str = ""
    type: str = "checking"


class FinanceEnvironment(TaskEnvironment):
    # BankManager
    user_name: str = "Morgan Chen"
    accounts: list[Account] = Field(default_factory=list)
    payees: list[Payee] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    scheduled_payments: list[ScheduledPayment] = Field(default_factory=list)
    bills: list[Bill] = Field(default_factory=list)
    transfers: list[Transfer] = Field(default_factory=list)
    bill_payments: list[BillPayment] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)          # generated statement files: path -> text
    contacts: dict[str, str] = Field(default_factory=dict)       # known recipient -> description (statement sharing)
    shared_statements: list[SharedStatement] = Field(default_factory=list)
    # Venmo
    venmo_username: str = "morgan-chen"
    venmo_balance: float = 0.0
    venmo_users: list[VenmoUser] = Field(default_factory=list)
    venmo_transactions: list[VenmoTransaction] = Field(default_factory=list)
    linked_accounts: list[LinkedAccount] = Field(default_factory=list)


def load_environment(path: str | Path) -> FinanceEnvironment:
    return FinanceEnvironment.model_validate(yaml.safe_load(Path(path).read_text()) or {})


def env_to_dict(env: FinanceEnvironment) -> dict:
    return env.model_dump(mode="json")
