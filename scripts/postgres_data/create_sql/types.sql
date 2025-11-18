-- ============================================
-- 2. CREATE CUSTOM TYPES (ENUMS)
-- ============================================

-- Harvest Protocol Type
DO $$ BEGIN
    CREATE TYPE harvest_protocol AS ENUM ('OAI-PMH', 'REST_API');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Resource Type
DO $$ BEGIN
    CREATE TYPE resource_type AS ENUM (
        'Audiovisual', 'Award', 'Book', 'BookChapter', 'Collection',
        'ComputationalNotebook', 'ConferencePaper', 'ConferenceProceeding',
        'DataPaper', 'Dataset', 'Dissertation', 'Event', 'Image',
        'InteractiveResource', 'Instrument', 'Journal', 'JournalArticle',
        'Model', 'OutputManagementPlan', 'PeerReview', 'PhysicalObject',
        'Preprint', 'Project', 'Report', 'Service', 'Software', 'Sound',
        'Standard', 'StudyRegistration', 'Text', 'Workflow', 'Other'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Content Format Type
DO $$ BEGIN
    CREATE TYPE content_format AS ENUM ('XML', 'JSON');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Harvest Run State
DO $$ BEGIN
    CREATE TYPE harvest_run_state AS ENUM ('open', 'closed', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
