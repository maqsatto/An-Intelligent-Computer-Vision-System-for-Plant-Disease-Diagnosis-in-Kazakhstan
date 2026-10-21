"""Enforce immutable terminal results, model pins and ready image metadata."""

from alembic import op

revision = "20261021_guards"
down_revision = "164136ed1b7d"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION protect_assessment() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'assessments are retained immutable records';
      END IF;
      IF OLD.status IN ('completed','failed') AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
        RAISE EXCEPTION 'terminal assessment is immutable';
      END IF;
      IF ROW(OLD.owner_id,OLD.observation_id,OLD.primary_photo_id,OLD.crop_id,OLD.organ,
             OLD.model::jsonb,OLD.bundle_manifest::jsonb,OLD.bundle_path,OLD.model_mode)
         IS DISTINCT FROM
         ROW(NEW.owner_id,NEW.observation_id,NEW.primary_photo_id,NEW.crop_id,NEW.organ,
             NEW.model::jsonb,NEW.bundle_manifest::jsonb,NEW.bundle_path,NEW.model_mode) THEN
        RAISE EXCEPTION 'assessment input and model pins are immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER assessment_immutable BEFORE UPDATE OR DELETE ON assessments
                  FOR EACH ROW EXECUTE FUNCTION protect_assessment()""")
    op.execute("""CREATE FUNCTION protect_ready_photo() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status='ready' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
        RAISE EXCEPTION 'ready photo is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER photo_immutable BEFORE UPDATE ON photos
                  FOR EACH ROW EXECUTE FUNCTION protect_ready_photo()""")


def downgrade():
    op.execute("DROP TRIGGER photo_immutable ON photos")
    op.execute("DROP FUNCTION protect_ready_photo()")
    op.execute("DROP TRIGGER assessment_immutable ON assessments")
    op.execute("DROP FUNCTION protect_assessment()")
