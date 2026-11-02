"""Все FSM-состояния в одном месте."""
from aiogram.fsm.state import State, StatesGroup


class DiaryStates(StatesGroup):
    lights_out = State()
    try_sleep = State()
    final_wake = State()
    sol = State()
    waso = State()
    awakenings = State()
    quality = State()
    factors_caffeine = State()
    factors_alcohol = State()
    factors_screen = State()
    factors_activity = State()
    factors_stress = State()
    notes = State()
    confirm = State()


class ISIStates(StatesGroup):
    question = State()
    confirm = State()


class PSQIStates(StatesGroup):
    c1_quality = State()
    c2_latency = State()
    c3_duration = State()
    c4_efficiency = State()
    c5_disturbances = State()
    confirm = State()


class ESSStates(StatesGroup):
    question = State()
    confirm = State()


class StopBangStates(StatesGroup):
    question = State()
    confirm = State()