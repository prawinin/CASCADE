from marshmallow import Schema, fields, validate, ValidationError  # noqa: E402

class Optimize3DParamsSchema(Schema):
    smiles = fields.Str(required=True, validate=validate.Length(min=1, max=2000))
    force_field = fields.Str(
        required=False,
        load_default="MMFF94",
        validate=validate.OneOf(["MMFF94", "MMFF94s", "UFF"])
    )
    job_id = fields.Str(required=False, allow_none=True)

class InteractionProfileParamsSchema(Schema):
    smiles = fields.Str(required=True, validate=validate.Length(min=1, max=2000))
    pdb_id = fields.Str(required=False, allow_none=True, validate=validate.Length(max=8))
    ligand_resname = fields.Str(required=True, validate=validate.Length(min=1, max=8))
    ligand_chain = fields.Str(required=False, allow_none=True, validate=validate.Length(max=4))
    ligand_seq = fields.Int(required=False, allow_none=True)
    job_id = fields.Str(required=False, allow_none=True)

class MDSimulationParamsSchema(Schema):
    sdf_path = fields.Str(required=False, allow_none=True)
    smiles = fields.Str(required=False, allow_none=True)
    n_steps = fields.Int(required=True, validate=validate.Range(min=1, max=10_000_000))
    job_id = fields.Str(required=False, allow_none=True)

class TaskSubmitSchema(Schema):
    task_type = fields.Str(
        required=True,
        validate=validate.OneOf(["optimize_3d", "interaction_profile", "md_simulation"])
    )
    params = fields.Dict(required=True)
    job_id = fields.Str(required=False, allow_none=True)

    def validate_params(self, data):
        task_type = data.get("task_type")
        params = data.get("params", {})
        
        try:
            if task_type == "optimize_3d":
                cleaned = Optimize3DParamsSchema().load(params)
            elif task_type == "interaction_profile":
                cleaned = InteractionProfileParamsSchema().load(params)
            elif task_type == "md_simulation":
                cleaned = MDSimulationParamsSchema().load(params)
            else:
                cleaned = {}
            data["params"] = cleaned
        except ValidationError as err:
            raise ValidationError(err.messages, field_name="params")
