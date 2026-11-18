"""Bit-exact software model of the engine_top_rb gamma lanes in LFSR mode (review fixes, part B).

gamma_src.sv (LFSR_MODE = 1): 16-bit Galois LFSR (taps 0xB400), advanced 16 steps per draw (leap16); after a draw,
  g8 = GMIN + #{b : CUM[b] <= u}, u = low 12 bits of the new state, CUM = {187, 791, 1395, 1999, 2603, 3207, 3811, 4096},
  GMIN = -2. The state is loaded with SEED only on rst; `start` sets g8 = G0 but keeps the state.
engine_top_rb.sv: lane (t, p) for type t (0..9) and position p (0..71) has SEED = (((t * 72 + p) + 1) * 0x9E37) mod 2^16.
  All 720 lanes draw together (lane_draw), so one global draw counter D indexes every lane's sequence.
  Draw schedule (ctrl_rb.sv, engine_top_rb.sv lines 192-212):
    - leg-end iteration of leg k issued (it_leg + 1 == leg_len) and k != NLEGS: pre_go -> 6 prefill draws for the odd home
      rounds 1, 3, ..., 11 of leg k + 1 (also when that iteration converges);
    - first iteration of leg k >= 1: one draw at each even init step, home rounds 0, 2, ..., 12 (7 draws).
  So leg k >= 1 uses draws [13 (k - 1) + j], j = 0..12, for home rounds (1, 3, 5, 7, 9, 11, 0, 2, 4, 6, 8, 10, 12),
  counted from the decode's starting counter D0; a decode with t iterations uses
    draws(t) = 13 L + (6 if the converging iteration is the last of its leg and L < 300 else 0),
    L = 0 if t <= 80 else 1 + (t - 81) // 60   (leg of the last iteration).
  Leg 0 uses g8 = G0 = 1 (= round(8 * 0.125)) in both hardware and software.
Software use: relay_bp.RelayDecoderF32(..., explicit_gammas=G) with G[k, j] = g8 / 8 for leg k (row 0 unused); with
  quant int4.2.8 the decoder rounds 8 * gamma back to the same g8.
"""
import numpy as np

TAPS = 0xB400
CUM = np.array([187, 791, 1395, 1999, 2603, 3207, 3811, 4096])
GMIN = -2
NT, NP, NR, NODD = 10, 72, 13, 6
PRE, LEG, NLEGS = 80, 60, 300
HOME_ORDER = [1, 3, 5, 7, 9, 11, 0, 2, 4, 6, 8, 10, 12]
POS_OF_HOME = {h: i for i, h in enumerate(HOME_ORDER)}


def seeds():
    return np.array([(((t * NP + p) + 1) * 0x9E37) & 0xFFFF for t in range(NT) for p in range(NP)], dtype=np.uint32)


def leap16(x):
    for _ in range(16):
        x = np.where(x & 1, (x >> 1) ^ TAPS, x >> 1)
    return x


def g8_of(state):
    return (GMIN + np.searchsorted(CUM, state & 0xFFF, side="right")).astype(np.int8)


def table(ndraws):
    """g8 of draws 1..ndraws for every lane (lane = t * 72 + p): int8 array (720, ndraws); also the final states."""
    s = seeds().copy()
    out = np.empty((NT * NP, ndraws), dtype=np.int8)
    for d in range(ndraws):
        s = leap16(s)
        out[:, d] = g8_of(s)
    return out, s


def period_table():
    """full-period table; asserts that every lane returns to its seed after the period (65,535 draws)."""
    T, s = table(65535)
    assert np.array_equal(s, seeds()), "LFSR leap-16 sequence does not have period 65,535"
    return T


def draws(it):
    L = 0 if it <= PRE else 1 + (it - PRE - 1) // LEG
    last_of_leg = (it == PRE) or (it > PRE and (it - PRE) % LEG == 0)
    return 13 * L + (6 if last_of_leg and L < NLEGS else 0)


def gamma_matrix(T, D0, lane_of_col, home_of_col, nlegs=NLEGS):
    """explicit_gammas (nlegs + 1, n): row k = leg k (k >= 1), g8 / 8 from the global draw counter D0."""
    per = T.shape[1]
    pos = np.array([POS_OF_HOME[int(h)] for h in home_of_col])
    k = np.arange(1, nlegs + 1)[:, None]
    idx = (D0 + 13 * (k - 1) + pos[None, :]) % per
    G = np.zeros((nlegs + 1, len(lane_of_col)))
    G[1:] = T[lane_of_col[None, :], idx] / 8.0
    return G
