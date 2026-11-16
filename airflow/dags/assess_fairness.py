import logging
import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from importlib.metadata import version

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Param, dag, get_current_context, task
from fair_offline_assessor import FairAssessor
from sqlalchemy import DateTime, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

logger = logging.getLogger(__name__)

POSTGRES_CONN_ID = 'datasetdb'
BATCH_SIZE = 100
MAX_PARALLEL_BATCHES = 4
LOAF_VERSION = version('fair-offline-assessor')


class Base(DeclarativeBase):
    pass


class FairOutcome(StrEnum):
    PASS = 'pass'  # noqa: S105
    FAIL = 'fail'
    PARTIAL = 'partial'
    INDETERMINATE = 'indeterminate'
    NOT_APPLICABLE = 'not_applicable'
    ERROR = 'error'
    UNAVAILABLE = 'unavailable'


fair_outcome = SQLEnum(
    FairOutcome,
    name='fair_outcome',
    values_callable=lambda enum: [e.value for e in enum],
)


class FairAssessment(Base):
    __tablename__ = 'fair_assessments'

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    record_id: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    pid: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    assessor: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    assessor_version: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    raw_assessment: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    # Findable
    f: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f3: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f4: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    # Accessible
    a: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a1_1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a1_2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    # Interoperable
    i: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    i1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    i2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    i3: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    # Reusable
    r: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1_1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1_2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1_3: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


CRITERION_COLUMNS = {
    'f1': 'F1',
    'f2': 'F2',
    'f3': 'F3',
    'f4': 'F4',
    'a1': 'A1',
    'a1_1': 'A1.1',
    'a1_2': 'A1.2',
    'a2': 'A2',
    'i1': 'I1',
    'i2': 'I2',
    'i3': 'I3',
    'r1': 'R1',
    'r1_1': 'R1.1',
    'r1_2': 'R1.2',
    'r1_3': 'R1.3',
}

PRINCIPLE_COLUMNS = {
    'f': ('f1', 'f2', 'f3', 'f4'),
    'a': ('a1', 'a1_1', 'a1_2', 'a2'),
    'i': ('i1', 'i2', 'i3'),
    'r': ('r1', 'r1_1', 'r1_2', 'r1_3'),
}


def aggregate_outcomes(outcomes) -> FairOutcome:
    # Missing criteria are unavailable; not_applicable is excluded.
    outcomes = [outcome for outcome in outcomes if outcome != FairOutcome.UNAVAILABLE]

    if not outcomes:
        return FairOutcome.UNAVAILABLE

    if FairOutcome.ERROR in outcomes:
        return FairOutcome.ERROR

    applicable = [outcome for outcome in outcomes if outcome != FairOutcome.NOT_APPLICABLE]

    if not applicable:
        return FairOutcome.NOT_APPLICABLE

    has_positive = any(outcome in {FairOutcome.PASS, FairOutcome.PARTIAL} for outcome in applicable)

    if FairOutcome.INDETERMINATE in applicable:
        return FairOutcome.PARTIAL if has_positive else FairOutcome.INDETERMINATE

    if all(outcome == FairOutcome.PASS for outcome in applicable):
        return FairOutcome.PASS

    if all(outcome == FairOutcome.FAIL for outcome in applicable):
        return FairOutcome.FAIL

    return FairOutcome.PARTIAL


def process_record(record_id: str, pid: str, xml: str) -> None:
    logger.info('Processing record %s', record_id)

    assessor = FairAssessor()
    full_result = assessor.assess(
        metadata=xml,
        metadata_format='xml',
    )

    data = full_result.model_dump(mode='json')
    summary = data.get('summary')

    if not summary:
        raise ValueError(f'Assessment summary missing for record {record_id}')

    # Populate individual FAIR criteria.
    criteria = {
        column: (FairOutcome(summary[criterion]['outcome']) if criterion in summary else FairOutcome.UNAVAILABLE)
        for column, criterion in CRITERION_COLUMNS.items()
    }

    # Aggregate overall F, A, I and R outcomes.
    principles = {
        principle: aggregate_outcomes(criteria[column] for column in columns)
        for principle, columns in PRINCIPLE_COLUMNS.items()
    }

    assessment = FairAssessment(
        record_id=record_id,
        pid=pid,
        assessor='loaf',
        assessor_version=LOAF_VERSION,
        raw_assessment=full_result.model_dump(mode='json'),
        **criteria,
        **principles,
    )

    engine = PostgresHook(
        postgres_conn_id=POSTGRES_CONN_ID,
    ).get_sqlalchemy_engine()

    try:
        with Session(engine, expire_on_commit=False) as session:
            session.add(assessment)
            session.commit()

        logger.info(
            'Saved FAIR assessment %s for DOI %s',
            assessment.id,
            assessment.pid,
        )
    finally:
        engine.dispose()


@dag(
    dag_id='process_datacite_records',
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=['fair'],
    params={
        'sample_size': Param(
            default=1000,
            type='integer',
            minimum=1,
            title='Number of random records',
            description='Number of records to randomly select and process.',
        ),
    },
)
def process_datacite_records():
    @task
    def init_fair_tables():
        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        engine = hook.get_sqlalchemy_engine()

        try:
            Base.metadata.create_all(bind=engine)
        finally:
            engine.dispose()

    @task
    def select_random_batches() -> list[list[str]]:
        sample_size = get_current_context()['params']['sample_size']

        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = hook.get_conn()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM public.records
                    WHERE raw_metadata IS NOT NULL
                    ORDER BY random()
                    LIMIT %s
                    """,
                    (sample_size,),
                )

                batches = []

                while records := cursor.fetchmany(BATCH_SIZE):
                    batches.append([str(record_id) for (record_id,) in records])

                logger.info(
                    'Selected %d batches',
                    len(batches),
                )
                return batches
        finally:
            conn.close()

    @task(
        retries=0,
        execution_timeout=timedelta(hours=2),
        max_active_tis_per_dag=MAX_PARALLEL_BATCHES,
    )
    def process_batch(record_ids: list[str]):
        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = hook.get_conn()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, record_identifier, raw_metadata
                    FROM public.records
                    WHERE id = ANY(%s)
                    """,
                    (record_ids,),
                )

                records = cursor.fetchall()

            for record_id, pid, raw_metadata in records:
                process_record(record_id, pid, raw_metadata)

            logger.info(
                'Processed batch of %d records',
                len(records),
            )
        finally:
            conn.close()

    init_task = init_fair_tables()
    batches = select_random_batches()

    init_task >> batches

    process_batch.expand(record_ids=batches)


process_datacite_records()
