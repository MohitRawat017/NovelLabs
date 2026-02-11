"""add_chapter_audio_tables

Revision ID: b4d55g4620f6
Revises: a3c44f3519e5
Create Date: 2026-02-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d55g4620f6'
down_revision: Union[str, Sequence[str], None] = 'a3c44f3519e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create chapter_audio and audio_timings tables."""
    
    # Create chapter_audio table for full chapter audio (concatenated)
    op.create_table(
        'chapter_audio',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('novel_slug', sa.String(length=255), nullable=False),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('voice', sa.String(length=50), server_default='af_heart', nullable=True),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=True),
        sa.Column('audio_url', sa.String(length=500), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('progress', sa.Integer(), server_default='0', nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create unique index for chapter_audio
    op.create_index(
        'idx_chapter_audio_lookup',
        'chapter_audio',
        ['novel_slug', 'chapter_number'],
        unique=True
    )
    
    # Create audio_timings table for karaoke highlighting
    op.create_table(
        'audio_timings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('novel_slug', sa.String(length=255), nullable=False),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index for audio_timings
    op.create_index(
        'idx_audio_timings_lookup',
        'audio_timings',
        ['novel_slug', 'chapter_number'],
        unique=False
    )
    
    # Create unique constraint for chunk_index within a chapter
    op.create_index(
        'idx_audio_timings_unique',
        'audio_timings',
        ['novel_slug', 'chapter_number', 'chunk_index'],
        unique=True
    )


def downgrade() -> None:
    """Drop chapter_audio and audio_timings tables."""
    op.drop_index('idx_audio_timings_unique', table_name='audio_timings')
    op.drop_index('idx_audio_timings_lookup', table_name='audio_timings')
    op.drop_table('audio_timings')
    
    op.drop_index('idx_chapter_audio_lookup', table_name='chapter_audio')
    op.drop_table('chapter_audio')
