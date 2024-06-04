"""
C++ Bindings for Fizz, a TLS 1.3 library from Facebook
"""
from __future__ import annotations
import typing
__all__ = ['FizzClientContext', 'NamedGroup', 'ProtocolVersion', 'SignatureScheme', 'ecdsa_secp256r1_sha256', 'ecdsa_secp256r1_sha256_batch', 'ecdsa_secp384r1_sha384', 'ecdsa_secp384r1_sha384_batch', 'ecdsa_secp521r1_sha512', 'ecdsa_secp521r1_sha512_batch', 'ed25519', 'ed25519_batch', 'ed448', 'ed448_batch', 'fizz_kyber512', 'fizz_secp256r1', 'fizz_secp256r1_kyber512', 'fizz_secp256r1_kyber768_draft00', 'fizz_secp384r1', 'fizz_secp384r1_kyber768', 'fizz_secp521r1', 'fizz_secp521r1_x25519', 'fizz_x25519', 'fizz_x25519_kyber512', 'fizz_x25519_kyber512_experimental', 'fizz_x25519_kyber768_draft00', 'fizz_x25519_kyber768_experimental', 'rsa_pss_sha256', 'rsa_pss_sha256_batch', 'rsa_pss_sha384', 'rsa_pss_sha512', 'tls_1_0', 'tls_1_1', 'tls_1_2', 'tls_1_3', 'tls_1_3_23', 'tls_1_3_23_fb', 'tls_1_3_26', 'tls_1_3_26_fb', 'tls_1_3_28']
class FizzClientContext:
    def __init__(self) -> None:
        ...
    def getDefaultShares(self) -> list[NamedGroup]:
        ...
    def getSupportedAlpns(self) -> list[str]:
        ...
    def getSupportedCiphers(self) -> list[...]:
        ...
    def getSupportedGroups(self) -> list[NamedGroup]:
        ...
    def getSupportedPskModes(self) -> list[...]:
        ...
    def getSupportedSigSchemes(self) -> list[SignatureScheme]:
        ...
    def getSupportedVersions(self) -> list[ProtocolVersion]:
        ...
    def setDefaultShares(self, arg0: list[NamedGroup]) -> None:
        ...
    def setSupportedAlpns(self, arg0: list[str]) -> None:
        ...
    def setSupportedCiphers(self, arg0: list[...]) -> None:
        ...
    def setSupportedGroups(self, arg0: list[NamedGroup]) -> None:
        ...
    def setSupportedPskModes(self, arg0: list[...]) -> None:
        ...
    def setSupportedSigSchemes(self, arg0: list[SignatureScheme]) -> None:
        ...
    def setSupportedVersions(self, arg0: list[ProtocolVersion]) -> None:
        ...
class NamedGroup:
    """
    Members:
    
      fizz_secp256r1
    
      fizz_secp384r1
    
      fizz_secp521r1
    
      fizz_x25519
    
      fizz_x25519_kyber768_draft00
    
      fizz_secp256r1_kyber768_draft00
    
      fizz_x25519_kyber768_experimental
    
      fizz_x25519_kyber512_experimental
    
      fizz_secp521r1_x25519
    
      fizz_x25519_kyber512
    
      fizz_secp256r1_kyber512
    
      fizz_kyber512
    
      fizz_secp384r1_kyber768
    """
    __members__: typing.ClassVar[dict[str, NamedGroup]]  # value = {'fizz_secp256r1': <NamedGroup.fizz_secp256r1: 23>, 'fizz_secp384r1': <NamedGroup.fizz_secp384r1: 24>, 'fizz_secp521r1': <NamedGroup.fizz_secp521r1: 25>, 'fizz_x25519': <NamedGroup.fizz_x25519: 29>, 'fizz_x25519_kyber768_draft00': <NamedGroup.fizz_x25519_kyber768_draft00: 25497>, 'fizz_secp256r1_kyber768_draft00': <NamedGroup.fizz_secp256r1_kyber768_draft00: 25498>, 'fizz_x25519_kyber768_experimental': <NamedGroup.fizz_x25519_kyber768_experimental: 65024>, 'fizz_x25519_kyber512_experimental': <NamedGroup.fizz_x25519_kyber512_experimental: 65025>, 'fizz_secp521r1_x25519': <NamedGroup.fizz_secp521r1_x25519: 510>, 'fizz_x25519_kyber512': <NamedGroup.fizz_x25519_kyber512: 12089>, 'fizz_secp256r1_kyber512': <NamedGroup.fizz_secp256r1_kyber512: 12090>, 'fizz_kyber512': <NamedGroup.fizz_kyber512: 511>, 'fizz_secp384r1_kyber768': <NamedGroup.fizz_secp384r1_kyber768: 12092>}
    fizz_kyber512: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_kyber512: 511>
    fizz_secp256r1: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_secp256r1: 23>
    fizz_secp256r1_kyber512: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_secp256r1_kyber512: 12090>
    fizz_secp256r1_kyber768_draft00: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_secp256r1_kyber768_draft00: 25498>
    fizz_secp384r1: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_secp384r1: 24>
    fizz_secp384r1_kyber768: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_secp384r1_kyber768: 12092>
    fizz_secp521r1: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_secp521r1: 25>
    fizz_secp521r1_x25519: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_secp521r1_x25519: 510>
    fizz_x25519: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_x25519: 29>
    fizz_x25519_kyber512: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_x25519_kyber512: 12089>
    fizz_x25519_kyber512_experimental: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_x25519_kyber512_experimental: 65025>
    fizz_x25519_kyber768_draft00: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_x25519_kyber768_draft00: 25497>
    fizz_x25519_kyber768_experimental: typing.ClassVar[NamedGroup]  # value = <NamedGroup.fizz_x25519_kyber768_experimental: 65024>
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: int) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: int) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class ProtocolVersion:
    """
    Members:
    
      tls_1_0
    
      tls_1_1
    
      tls_1_2
    
      tls_1_3
    
      tls_1_3_23
    
      tls_1_3_23_fb
    
      tls_1_3_26
    
      tls_1_3_26_fb
    
      tls_1_3_28
    """
    __members__: typing.ClassVar[dict[str, ProtocolVersion]]  # value = {'tls_1_0': <ProtocolVersion.tls_1_0: 769>, 'tls_1_1': <ProtocolVersion.tls_1_1: 770>, 'tls_1_2': <ProtocolVersion.tls_1_2: 771>, 'tls_1_3': <ProtocolVersion.tls_1_3: 772>, 'tls_1_3_23': <ProtocolVersion.tls_1_3_23: 32535>, 'tls_1_3_23_fb': <ProtocolVersion.tls_1_3_23_fb: 64279>, 'tls_1_3_26': <ProtocolVersion.tls_1_3_26: 32538>, 'tls_1_3_26_fb': <ProtocolVersion.tls_1_3_26_fb: 64282>, 'tls_1_3_28': <ProtocolVersion.tls_1_3_28: 32540>}
    tls_1_0: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_0: 769>
    tls_1_1: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_1: 770>
    tls_1_2: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_2: 771>
    tls_1_3: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_3: 772>
    tls_1_3_23: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_3_23: 32535>
    tls_1_3_23_fb: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_3_23_fb: 64279>
    tls_1_3_26: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_3_26: 32538>
    tls_1_3_26_fb: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_3_26_fb: 64282>
    tls_1_3_28: typing.ClassVar[ProtocolVersion]  # value = <ProtocolVersion.tls_1_3_28: 32540>
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: int) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: int) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class SignatureScheme:
    """
    Members:
    
      ecdsa_secp256r1_sha256
    
      ecdsa_secp384r1_sha384
    
      ecdsa_secp521r1_sha512
    
      rsa_pss_sha256
    
      rsa_pss_sha384
    
      rsa_pss_sha512
    
      ed25519
    
      ed448
    
      ecdsa_secp256r1_sha256_batch
    
      ecdsa_secp384r1_sha384_batch
    
      ecdsa_secp521r1_sha512_batch
    
      ed25519_batch
    
      ed448_batch
    
      rsa_pss_sha256_batch
    """
    __members__: typing.ClassVar[dict[str, SignatureScheme]]  # value = {'ecdsa_secp256r1_sha256': <SignatureScheme.ecdsa_secp256r1_sha256: 1027>, 'ecdsa_secp384r1_sha384': <SignatureScheme.ecdsa_secp384r1_sha384: 1283>, 'ecdsa_secp521r1_sha512': <SignatureScheme.ecdsa_secp521r1_sha512: 1539>, 'rsa_pss_sha256': <SignatureScheme.rsa_pss_sha256: 2052>, 'rsa_pss_sha384': <SignatureScheme.rsa_pss_sha384: 2053>, 'rsa_pss_sha512': <SignatureScheme.rsa_pss_sha512: 2054>, 'ed25519': <SignatureScheme.ed25519: 2055>, 'ed448': <SignatureScheme.ed448: 2056>, 'ecdsa_secp256r1_sha256_batch': <SignatureScheme.ecdsa_secp256r1_sha256_batch: 65024>, 'ecdsa_secp384r1_sha384_batch': <SignatureScheme.ecdsa_secp384r1_sha384_batch: 65025>, 'ecdsa_secp521r1_sha512_batch': <SignatureScheme.ecdsa_secp521r1_sha512_batch: 65026>, 'ed25519_batch': <SignatureScheme.ed25519_batch: 65027>, 'ed448_batch': <SignatureScheme.ed448_batch: 65028>, 'rsa_pss_sha256_batch': <SignatureScheme.rsa_pss_sha256_batch: 65029>}
    ecdsa_secp256r1_sha256: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ecdsa_secp256r1_sha256: 1027>
    ecdsa_secp256r1_sha256_batch: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ecdsa_secp256r1_sha256_batch: 65024>
    ecdsa_secp384r1_sha384: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ecdsa_secp384r1_sha384: 1283>
    ecdsa_secp384r1_sha384_batch: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ecdsa_secp384r1_sha384_batch: 65025>
    ecdsa_secp521r1_sha512: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ecdsa_secp521r1_sha512: 1539>
    ecdsa_secp521r1_sha512_batch: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ecdsa_secp521r1_sha512_batch: 65026>
    ed25519: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ed25519: 2055>
    ed25519_batch: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ed25519_batch: 65027>
    ed448: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ed448: 2056>
    ed448_batch: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.ed448_batch: 65028>
    rsa_pss_sha256: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.rsa_pss_sha256: 2052>
    rsa_pss_sha256_batch: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.rsa_pss_sha256_batch: 65029>
    rsa_pss_sha384: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.rsa_pss_sha384: 2053>
    rsa_pss_sha512: typing.ClassVar[SignatureScheme]  # value = <SignatureScheme.rsa_pss_sha512: 2054>
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: int) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: int) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
ecdsa_secp256r1_sha256: SignatureScheme  # value = <SignatureScheme.ecdsa_secp256r1_sha256: 1027>
ecdsa_secp256r1_sha256_batch: SignatureScheme  # value = <SignatureScheme.ecdsa_secp256r1_sha256_batch: 65024>
ecdsa_secp384r1_sha384: SignatureScheme  # value = <SignatureScheme.ecdsa_secp384r1_sha384: 1283>
ecdsa_secp384r1_sha384_batch: SignatureScheme  # value = <SignatureScheme.ecdsa_secp384r1_sha384_batch: 65025>
ecdsa_secp521r1_sha512: SignatureScheme  # value = <SignatureScheme.ecdsa_secp521r1_sha512: 1539>
ecdsa_secp521r1_sha512_batch: SignatureScheme  # value = <SignatureScheme.ecdsa_secp521r1_sha512_batch: 65026>
ed25519: SignatureScheme  # value = <SignatureScheme.ed25519: 2055>
ed25519_batch: SignatureScheme  # value = <SignatureScheme.ed25519_batch: 65027>
ed448: SignatureScheme  # value = <SignatureScheme.ed448: 2056>
ed448_batch: SignatureScheme  # value = <SignatureScheme.ed448_batch: 65028>
fizz_kyber512: NamedGroup  # value = <NamedGroup.fizz_kyber512: 511>
fizz_secp256r1: NamedGroup  # value = <NamedGroup.fizz_secp256r1: 23>
fizz_secp256r1_kyber512: NamedGroup  # value = <NamedGroup.fizz_secp256r1_kyber512: 12090>
fizz_secp256r1_kyber768_draft00: NamedGroup  # value = <NamedGroup.fizz_secp256r1_kyber768_draft00: 25498>
fizz_secp384r1: NamedGroup  # value = <NamedGroup.fizz_secp384r1: 24>
fizz_secp384r1_kyber768: NamedGroup  # value = <NamedGroup.fizz_secp384r1_kyber768: 12092>
fizz_secp521r1: NamedGroup  # value = <NamedGroup.fizz_secp521r1: 25>
fizz_secp521r1_x25519: NamedGroup  # value = <NamedGroup.fizz_secp521r1_x25519: 510>
fizz_x25519: NamedGroup  # value = <NamedGroup.fizz_x25519: 29>
fizz_x25519_kyber512: NamedGroup  # value = <NamedGroup.fizz_x25519_kyber512: 12089>
fizz_x25519_kyber512_experimental: NamedGroup  # value = <NamedGroup.fizz_x25519_kyber512_experimental: 65025>
fizz_x25519_kyber768_draft00: NamedGroup  # value = <NamedGroup.fizz_x25519_kyber768_draft00: 25497>
fizz_x25519_kyber768_experimental: NamedGroup  # value = <NamedGroup.fizz_x25519_kyber768_experimental: 65024>
rsa_pss_sha256: SignatureScheme  # value = <SignatureScheme.rsa_pss_sha256: 2052>
rsa_pss_sha256_batch: SignatureScheme  # value = <SignatureScheme.rsa_pss_sha256_batch: 65029>
rsa_pss_sha384: SignatureScheme  # value = <SignatureScheme.rsa_pss_sha384: 2053>
rsa_pss_sha512: SignatureScheme  # value = <SignatureScheme.rsa_pss_sha512: 2054>
tls_1_0: ProtocolVersion  # value = <ProtocolVersion.tls_1_0: 769>
tls_1_1: ProtocolVersion  # value = <ProtocolVersion.tls_1_1: 770>
tls_1_2: ProtocolVersion  # value = <ProtocolVersion.tls_1_2: 771>
tls_1_3: ProtocolVersion  # value = <ProtocolVersion.tls_1_3: 772>
tls_1_3_23: ProtocolVersion  # value = <ProtocolVersion.tls_1_3_23: 32535>
tls_1_3_23_fb: ProtocolVersion  # value = <ProtocolVersion.tls_1_3_23_fb: 64279>
tls_1_3_26: ProtocolVersion  # value = <ProtocolVersion.tls_1_3_26: 32538>
tls_1_3_26_fb: ProtocolVersion  # value = <ProtocolVersion.tls_1_3_26_fb: 64282>
tls_1_3_28: ProtocolVersion  # value = <ProtocolVersion.tls_1_3_28: 32540>
