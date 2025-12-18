type JobResult = {
  outputPath?: string;
  downloadUrl?: string;
};

const JOBS = new Map<string, JobResult>();

export const setJobResult = (jobId: string, result: JobResult) => {
  JOBS.set(jobId, result);
};

export const getJobResult = (jobId: string) => JOBS.get(jobId);

export const deleteJobResult = (jobId: string) => {
  JOBS.delete(jobId);
};
