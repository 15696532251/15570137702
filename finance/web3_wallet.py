"""Wallet management: account loading, gas estimation, nonce tracking, signing."""

import os
import time
from typing import Optional
from web3 import Web3
from web3.types import TxParams


class Web3Wallet:
    """Manages a single EOA wallet for on-chain trading.

    Private key is NEVER stored in code — load from env var or encrypted file.

    Usage:
        wallet = Web3Wallet.from_env("PRIVATE_KEY", w3)
        wallet = Web3Wallet.from_keyfile("keystore.json", password, w3)
    """

    def __init__(self, private_key: str, w3: Web3):
        self._account = w3.eth.account.from_key(private_key)
        self.w3 = w3
        self.address: str = self._account.address
        self._nonce_cache: Optional[int] = None
        self._nonce_cache_block: int = 0

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls, env_var: str, w3: Web3) -> "Web3Wallet":
        """Load private key from environment variable."""
        key = os.environ.get(env_var)
        if not key:
            raise EnvironmentError(
                f"Environment variable '{env_var}' not set. "
                "Export your private key: export PRIVATE_KEY=0x..."
            )
        return cls(key, w3)

    @classmethod
    def from_keyfile(cls, path: str, password: str, w3: Web3) -> "Web3Wallet":
        """Load encrypted Ethereum keystore file (eth_account format)."""
        import json
        with open(path) as f:
            keystore = json.load(f)
        key = w3.eth.account.decrypt(keystore, password)
        return cls(key.hex(), w3)

    # ── Balance queries ───────────────────────────────────────────────────────

    def native_balance(self) -> float:
        """ETH/BNB/MATIC balance in ether units."""
        wei = self.w3.eth.get_balance(self.address)
        return float(self.w3.from_wei(wei, "ether"))

    def token_balance(self, token_address: str, abi: list) -> tuple:
        """Returns (balance_human, decimals) for an ERC-20 token."""
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=abi
        )
        raw = contract.functions.balanceOf(self.address).call()
        decimals = contract.functions.decimals().call()
        return raw / (10 ** decimals), decimals

    # ── Nonce management ──────────────────────────────────────────────────────

    def nonce(self) -> int:
        """Thread-safe nonce: fetches from chain, increments locally for burst."""
        current_block = self.w3.eth.block_number
        if self._nonce_cache is None or current_block > self._nonce_cache_block:
            self._nonce_cache = self.w3.eth.get_transaction_count(
                self.address, "pending"
            )
            self._nonce_cache_block = current_block
        n = self._nonce_cache
        self._nonce_cache += 1
        return n

    def reset_nonce(self) -> None:
        self._nonce_cache = None

    # ── Gas pricing ───────────────────────────────────────────────────────────

    def gas_params(self, priority_gwei: float = 1.5) -> dict:
        """EIP-1559 gas params (falls back to legacy if not supported)."""
        try:
            latest = self.w3.eth.get_block("latest")
            base_fee = latest.get("baseFeePerGas", 0)
            max_priority = self.w3.to_wei(priority_gwei, "gwei")
            max_fee = base_fee * 2 + max_priority
            return {
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": max_priority,
            }
        except Exception:
            # Legacy chains (BSC)
            gas_price = self.w3.eth.gas_price
            return {"gasPrice": int(gas_price * 1.1)}

    def estimate_gas(self, tx: TxParams, buffer: float = 1.2) -> int:
        """Estimate gas with a safety buffer multiplier."""
        try:
            estimated = self.w3.eth.estimate_gas(tx)
            return int(estimated * buffer)
        except Exception:
            return 300_000  # fallback

    # ── Transaction signing and sending ──────────────────────────────────────

    def build_tx(
        self,
        to: str,
        data: bytes = b"",
        value: int = 0,
        gas: Optional[int] = None,
        priority_gwei: float = 1.5,
    ) -> TxParams:
        chain_id = self.w3.eth.chain_id
        tx: TxParams = {
            "from":    self.address,
            "to":      Web3.to_checksum_address(to),
            "value":   value,
            "data":    data,
            "nonce":   self.nonce(),
            "chainId": chain_id,
        }
        tx.update(self.gas_params(priority_gwei))
        tx["gas"] = gas or self.estimate_gas(tx)
        return tx

    def sign_and_send(self, tx: TxParams) -> str:
        """Sign and broadcast a transaction. Returns tx hash (hex)."""
        signed = self._account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash.hex()

    def wait_for_receipt(
        self, tx_hash: str, timeout: int = 120, poll_interval: float = 2.0
    ) -> dict:
        """Block until tx is mined. Raises TimeoutError if not mined in time."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    return dict(receipt)
            except Exception:
                pass
            time.sleep(poll_interval)
        raise TimeoutError(f"Tx {tx_hash} not mined within {timeout}s")

    def send_and_wait(self, tx: TxParams, timeout: int = 120) -> dict:
        """Sign, send, and wait for confirmation. Returns receipt."""
        tx_hash = self.sign_and_send(tx)
        receipt = self.wait_for_receipt(tx_hash, timeout=timeout)
        if receipt.get("status") == 0:
            raise RuntimeError(f"Transaction reverted: {tx_hash}")
        return receipt

    def approve_token(
        self,
        token_address: str,
        spender: str,
        amount: int,
        token_abi: list,
    ) -> Optional[str]:
        """Approve spender for token if allowance is insufficient. Returns tx hash or None."""
        token = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address), abi=token_abi
        )
        current = token.functions.allowance(
            self.address, Web3.to_checksum_address(spender)
        ).call()
        if current >= amount:
            return None  # already approved

        data = token.encodeABI("approve", args=[
            Web3.to_checksum_address(spender), amount
        ])
        tx = self.build_tx(to=token_address, data=data)
        tx_hash = self.sign_and_send(tx)
        self.wait_for_receipt(tx_hash)
        return tx_hash
