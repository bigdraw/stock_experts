"""Data validation layer for stock indicators.

Validates that data values are within reasonable ranges before storing to database.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.services.data.provider import StockBasicIndicators

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of data validation."""
    is_valid: bool
    warnings: list[str]
    errors: list[str]


class IndicatorValidator:
    """Validates stock indicator data for reasonable values."""
    
    # Reasonable ranges for indicators
    RANGES = {
        'price': (0.01, 100000),  # 股价范围：0.01 - 100000 元
        'pe_ratio': (-10000, 10000),  # PE 范围：-10000 到 10000（负值表示亏损）
        'pb_ratio': (0, 1000),  # PB 范围：0 到 1000
        'market_cap': (0, 1e10),  # 市值范围：0 到 100 亿万元（即 100 万亿元）
        'circulating_market_cap': (0, 1e10),  # 流通市值范围同上
        'volume': (0, 1e12),  # 成交量范围：0 到 1 万亿股
        'amount': (0, 1e15),  # 成交额范围：0 到 1000 万亿元
        'turnover_ratio': (0, 100),  # 换手率范围：0% 到 100%
        'change_pct': (-20, 20),  # 涨跌幅范围：-20% 到 20%（考虑 ST 股票）
    }
    
    @classmethod
    def validate(cls, ind: StockBasicIndicators) -> ValidationResult:
        """Validate a stock's indicators.
        
        Args:
            ind: StockBasicIndicators instance to validate
            
        Returns:
            ValidationResult with is_valid flag and any warnings/errors
        """
        warnings = []
        errors = []
        
        # Validate price
        if ind.price is not None:
            if ind.price <= 0:
                errors.append(f"Invalid price: {ind.price} (must be > 0)")
            elif ind.price < cls.RANGES['price'][0] or ind.price > cls.RANGES['price'][1]:
                warnings.append(f"Price out of range: {ind.price}")
        
        # Validate PE ratio
        if ind.pe_ratio is not None:
            if ind.pe_ratio < cls.RANGES['pe_ratio'][0] or ind.pe_ratio > cls.RANGES['pe_ratio'][1]:
                warnings.append(f"PE ratio out of range: {ind.pe_ratio}")
        
        # Validate PB ratio
        if ind.pb_ratio is not None:
            if ind.pb_ratio < 0:
                errors.append(f"Invalid PB ratio: {ind.pb_ratio} (must be >= 0)")
            elif ind.pb_ratio > cls.RANGES['pb_ratio'][1]:
                warnings.append(f"PB ratio out of range: {ind.pb_ratio}")
        
        # Validate market cap (in 万元)
        if ind.market_cap is not None:
            if ind.market_cap < 0:
                errors.append(f"Invalid market cap: {ind.market_cap} (must be >= 0)")
            elif ind.market_cap > cls.RANGES['market_cap'][1]:
                warnings.append(f"Market cap out of range: {ind.market_cap}")
            # Sanity check: market cap should be at least 1000 万元 (10 million yuan)
            elif ind.market_cap < 1000:
                warnings.append(f"Suspiciously low market cap: {ind.market_cap} 万元")
        
        # Validate circulating market cap
        if ind.circulating_market_cap is not None:
            if ind.circulating_market_cap < 0:
                errors.append(f"Invalid circulating market cap: {ind.circulating_market_cap}")
            elif ind.circulating_market_cap > cls.RANGES['circulating_market_cap'][1]:
                warnings.append(f"Circulating market cap out of range: {ind.circulating_market_cap}")
        
        # Validate volume
        if ind.volume is not None:
            if ind.volume < 0:
                errors.append(f"Invalid volume: {ind.volume} (must be >= 0)")
        
        # Validate amount
        if ind.amount is not None:
            if ind.amount < 0:
                errors.append(f"Invalid amount: {ind.amount} (must be >= 0)")
        
        # Validate turnover ratio
        if ind.turnover_ratio is not None:
            if ind.turnover_ratio < 0 or ind.turnover_ratio > cls.RANGES['turnover_ratio'][1]:
                warnings.append(f"Turnover ratio out of range: {ind.turnover_ratio}")
        
        # Validate change percentage
        if ind.change_pct is not None:
            if ind.change_pct < cls.RANGES['change_pct'][0] or ind.change_pct > cls.RANGES['change_pct'][1]:
                warnings.append(f"Change percentage out of range: {ind.change_pct}")
        
        # Cross-validation: circulating market cap should be <= total market cap
        if ind.market_cap is not None and ind.circulating_market_cap is not None:
            if ind.circulating_market_cap > ind.market_cap:
                warnings.append(
                    f"Circulating market cap ({ind.circulating_market_cap}) > "
                    f"total market cap ({ind.market_cap})"
                )
        
        is_valid = len(errors) == 0
        
        if errors:
            logger.warning(f"Validation errors for {ind.code}: {errors}")
        if warnings:
            logger.debug(f"Validation warnings for {ind.code}: {warnings}")
        
        return ValidationResult(is_valid=is_valid, warnings=warnings, errors=errors)
    
    @classmethod
    def validate_batch(cls, indicators: list[StockBasicIndicators]) -> dict:
        """Validate a batch of indicators and return summary statistics.
        
        Args:
            indicators: List of StockBasicIndicators to validate
            
        Returns:
            Dict with validation summary
        """
        total = len(indicators)
        valid_count = 0
        warning_count = 0
        error_count = 0
        
        for ind in indicators:
            result = cls.validate(ind)
            if result.is_valid:
                valid_count += 1
            else:
                error_count += 1
            if result.warnings:
                warning_count += 1
        
        summary = {
            'total': total,
            'valid': valid_count,
            'warnings': warning_count,
            'errors': error_count,
            'valid_rate': valid_count / total if total > 0 else 0,
        }
        
        logger.info(
            f"Validation summary: {summary['valid']}/{summary['total']} valid "
            f"({summary['valid_rate']:.1%}), {summary['warnings']} warnings, "
            f"{summary['errors']} errors"
        )
        
        return summary
