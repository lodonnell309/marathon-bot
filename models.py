import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from typing import Optional, List
from datetime import datetime, date

# A base class for declarative table definitions.
# All ORM models will inherit from this.
Base = declarative_base()

class Token(Base):
    """
    SQLAlchemy model for storing Strava athlete tokens.
    """
    __tablename__ = 'tokens'

    # The primary key is the Strava athlete ID, using BigInteger for large IDs
    athlete_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    access_token: Mapped[str] = mapped_column(sa.String, nullable=False)
    refresh_token: Mapped[str] = mapped_column(sa.String, nullable=False)
    expires_at: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # The telegram_chat_id should also be BigInteger and nullable
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(sa.BigInteger, nullable=True, unique=True)
    
    def __repr__(self) -> str:
        return f"<Token(athlete_id={self.athlete_id})>"

class Activity(Base):
    """
    SQLAlchemy model for storing Strava activities.
    """
    __tablename__ = 'activities'
    
    # The primary key is the Strava activity ID, using BigInteger
    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('tokens.athlete_id'))
    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    type: Mapped[str] = mapped_column(sa.String, nullable=False)
    # Using DateTime(timezone=True) for timezone-aware storage in PostgreSQL
    start_date_local: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    distance_meters: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    distance_miles: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    moving_time_seconds: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    moving_time_minutes: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    average_heartrate: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    max_heartrate: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Activity(id={self.id}, name='{self.name}')>"

class MarathonPlan(Base):
    """
    SQLAlchemy model for storing marathon training plans.
    """
    __tablename__ = 'marathon_plan'
    
    # Composite primary key of athlete_id and date
    athlete_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('tokens.athlete_id'), primary_key=True)
    # Using String for date as the original code used TEXT
    date: Mapped[str] = mapped_column(sa.String, primary_key=True)
    run_type: Mapped[str] = mapped_column(sa.String)
    distance_miles: Mapped[Optional[float]] = mapped_column(sa.Float)

    def __repr__(self) -> str:
        return f"<MarathonPlan(athlete_id={self.athlete_id}, date='{self.date}')>"

class Meal(Base):
    """
    SQLAlchemy model for storing meal nutrition data.
    """
    __tablename__ = 'meals'

    # Using BigInteger for meal_id to be safe
    meal_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    meal_name: Mapped[str] = mapped_column(sa.String, nullable=False)
    date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    protein_grams: Mapped[Optional[float]] = mapped_column(sa.Float)
    carbs_grams: Mapped[Optional[float]] = mapped_column(sa.Float)
    fat_grams: Mapped[Optional[float]] = mapped_column(sa.Float)
    calories: Mapped[Optional[float]] = mapped_column(sa.Float)
    athlete_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('tokens.athlete_id'))

    def __repr__(self) -> str:
        return f"<Meal(meal_id={self.meal_id}, meal_name='{self.meal_name}')>"

class UserTarget(Base):
    """
    SQLAlchemy model for storing user nutrition targets.
    """
    __tablename__ = 'user_targets'

    athlete_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey('tokens.athlete_id'), primary_key=True)
    target_protein_grams: Mapped[Optional[float]] = mapped_column(sa.Float)
    target_carbs_grams: Mapped[Optional[float]] = mapped_column(sa.Float)
    target_fat_grams: Mapped[Optional[float]] = mapped_column(sa.Float)
    target_calories: Mapped[Optional[float]] = mapped_column(sa.Float)

    def __repr__(self) -> str:
        return f"<UserTarget(athlete_id={self.athlete_id})>"
