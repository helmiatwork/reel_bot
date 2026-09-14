require 'rails_helper'

RSpec.describe VideoProject, type: :model do
  describe 'validations' do
    subject { build(:video_project) }

    it 'is valid with valid attributes' do
      expect(subject).to be_valid
    end

    it 'requires a title' do
      subject.title = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:title]).to include("can't be blank")
    end

    it 'requires a status' do
      subject.status = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:status]).to include("can't be blank")
    end
  end

  describe 'status enum' do
    it 'defaults to draft' do
      project = described_class.new
      expect(project.status).to eq('draft')
    end

    it 'supports valid status values' do
      project = create(:video_project)
      expect(project).to be_draft

      project.script_generated!
      expect(project).to be_script_generated

      project.rendering!
      expect(project).to be_rendering

      project.completed!
      expect(project).to be_completed

      project.failed!
      expect(project).to be_failed
    end

    it 'rejects invalid status values' do
      expect {
        build(:video_project, status: 'invalid_status')
      }.to raise_error(ArgumentError)
    end
  end

  describe 'associations' do
    it 'has many pipeline_runs with dependent destroy' do
      project = create(:video_project)
      run = create(:pipeline_run, video_project: project)

      expect(project.pipeline_runs).to include(run)

      expect {
        project.destroy
      }.to change(PipelineRun, :count).by(-1)
    end
  end

  describe 'jsonb script attribute' do
    it 'stores and retrieves structured JSON data' do
      script_data = {
        'scenes' => [
          { 'scene_number' => 1, 'text' => 'Hook opening', 'duration' => 3.5 },
          { 'scene_number' => 2, 'text' => 'Main content', 'duration' => 12.0 }
        ]
      }
      project = create(:video_project, script: script_data)
      project.reload

      expect(project.script).to eq(script_data)
    end
  end
end
