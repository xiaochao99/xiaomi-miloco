# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Miloco Service 核心包
"""
from thespian.actors import ActorSystem

actor_system = ActorSystem()

__all__ = ['actor_system']
