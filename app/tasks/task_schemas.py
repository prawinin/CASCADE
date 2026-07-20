from marshmallow import Schema, fields, validate, ValidationError  # noqa: E402

class Optimize3DParamsSchema(Schema):
    smiles = fields.Str(required=True, validate=validate.Length(min=1))
    force_field = fields.Str(
        required=False,
        load_default="MMFF94",
        validate=validate.OneOf(["MMFF94", "MMFF94s", "UFF", "OPLS-AA", "OPLS_2005"])
    )

class InteractionProfileParamsSchema(Schema):
    smiles = fields.Str(required=True, validate=validate.Length(min=1))
    pdb_id = fields.Str(required=False, allow_none=True)
    ligand_resname = fields.Str(required=True, validate=validate.Length(min=1))
    ligand_chain = fields.Str(required=False, allow_none=True)
    ligand_seq = fields.Int(required=False, allow_none=True)

class MDSimulationParamsSchema(Schema):
    sdf_path = fields.Str(required=False, allow_none=True)
    smiles = fields.Str(required=False, allow_none=True)
    n_steps = fields.Int(required=True, validate=validate.Range(min=1))

class TaskSubmitSchema(Schema):
    task_type = fields.Str(
        required=True,
        validate=validate.OneOf(["optimize_3d", "interaction_profile", "md_simulation"])
    )
    params = fields.Dict(required=True)

    def validate_params(self, data):
        task_type = data.get("task_type")
        params = data.get("params", {})
        
        try:
            if task_type == "optimize_3d":
                Optimize3DParamsSchema().load(params)
            elif task_type == "interaction_profile":
                InteractionProfileParamsSchema().load(params)
            elif task_type == "md_simulation":
                MDSimulationParamsSchema().load(params)
        except ValidationError as err:
            raise ValidationError(err.messages, field_name="params")
